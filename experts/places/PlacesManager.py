import json
import os
import sys
import numpy
from PIL import Image
from queue import Queue
from argparse import ArgumentParser
from logging import Logger

from .PlacesAPIUtility import PlacesAPIUtility
# from .models import PlacesModel
from .models.model_factory import create_places_model
from common.constants import *
# import from common
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.ExpertManager import (ExpertManager, ExpertPipeline, ExpertPipelineStep, CLI_command, global_config,
                                  AggQueue, OUTPUT_STYLE_ANNO, OUTPUT_STYLE_ARANGO, OUTPUT_STYLE_JSON)
from common.video_util import VideoInfo

#
# task message keys
# VIDEO_PATH_KEY = 'video_path'
# IS_REMOTE_KEY = 'is_remote'
# FPS_KEY = 'fps'
# NUM_FRAMES = 'num_frames'

PLACES_MODEL_NAME = os.getenv('PLACES_MODEL_NAME', 'places365')
PLACES_DETECTOR = 'Placess Detector'


class PlacesManager(ExpertManager):

    def initialize(self):
        self.api = PlacesAPIUtility()
        self.cur_task = None
        self.places_model = create_places_model(PLACES_MODEL_NAME)

    def get_pipeline(self) -> ExpertPipeline:
        places_step = PlacesStep(PLACES_DETECTOR)
        if self.args.arango:
            arango_step = ArangoStep('Scheduler', is_daemon=True)
            return ExpertPipeline([(arango_step, places_step)])
        else:
            return ExpertPipeline([(places_step, places_step)])

    @CLI_command
    def local(self, line):
        """run places detection on local movie file or frames directory, e.g.: local /movies/scenecliptest00581.avi"""
        if os.path.exists(line):
            pipeline_expert_q = self.pipeline.incoming_queues[PLACES_DETECTOR]
            try:
                pipeline_expert_q.put(self._get_video_msg(line, is_remote=False))
            except:
                self.logger.exception(f'bad video path "{line}"')
        else:
            self.print_n_log(f'path {line} does not exist')

    @CLI_command
    def remote(self, line):
        """run places detection on remote movie file, e.g.: remote Movies/92354428"""
        try:
            self.api.get_movie_info(line)  # check for movie info. if no error then movie exists
            pipeline_expert_q = self.pipeline.incoming_queues[PLACES_DETECTOR]
            pipeline_expert_q.put(self._get_video_msg(line, is_remote=True))
        except ValueError:
            self.logger.exception(f'remote movie does not exist')

    @CLI_command
    def tasks(self, line=''):
        """view enqueued tasks"""
        pipeline_expert_q = self.pipeline.incoming_queues[PLACES_DETECTOR]
        self.print_n_log(f'tasks queue: {list(pipeline_expert_q.queue)}')
        self.print_n_log(f'cur task: {self.cur_task}')


    def _get_video_msg(self, video_path, is_remote):
        msg = {VIDEO_PATH_KEY: video_path, IS_REMOTE_KEY: is_remote}
        msg.update(self.get_current_config())

        # video_info = VideoInfo(video_path)
        # msg[FPS_KEY] = video_info.fps if video_info.fps else self.default_fps.get()
        # msg[NUM_FRAMES] = video_info.num_frames

        return msg

    # class default_fps(global_config):
    #     def __init__(self, default_value=25):
    #         super().__init__(default_value)

    #     def set(self, new_value: str):
    #         new_value_int = int(new_value)
    #         assert new_value_int > 0
    #         self._value = new_value_int


class PlacesStep(ExpertPipelineStep):
    def run(self, q_in: Queue, q_out: AggQueue):
        self.mgr.print_n_log('places thread ready for input')

        # iterate until STOP message
        for msg in iter(q_in.get, self.pipeline.STOP_MSG):
            # set current video path
            video_path = msg[VIDEO_PATH_KEY]
            self.cur_task = video_path

            # get the movie data
            movie_entity = self.api.get_movie_entity(video_path)
            if movie_entity is None:
                self.logger.error(f'movie {video_path} was not found in db')
                continue

            # now collect only the frames we need
            self.logger.info(f'getting needed frame for movie: {video_path}')
            mdfs = movie_entity['mdfs']
            if mdfs is None:
                self.logger.error(f'movie {video_path} has not mdfs')
                continue
            frame_numbers = list(numpy.concatenate(mdfs).flat)
            frame_names = ['frame{:04d}.jpg'.format(fn) for fn in frame_numbers] # {:03d}'.format(n)
            num_frames = self.mgr.api.downloadFilesFroms3(video_path, frame_names)
            if num_frames == 0:
                self.logger.error(f'no frames found under the name {video_path}')
                self.cur_task = None  # if no frames are found, empty current task indicator
                continue

            self.logger.info(f'starting places detection: {video_path}')
            frames_model = []
            for scene_frames in mdfs:
                scene_places = []
                for scene_frame in scene_frames:
                    fname = 'frame{:04d}.jpg'.format(scene_frame)
                    frame_file = f'/workspaces/NEBULA2/{video_path}/{fname}'
                    img = Image.open(frame_file)
                    frame_model = self.mgr.places_model.forward(img)
                    if frame_model:
                        scene_places.append({scene_frame: frame_model})
                if len(scene_places):
                    frames_model.append(scene_places)


            if len(frames_model) == 0:
                self.logger.error(f'failed to detect places for: {video_path}')
                continue
            # create places model
            places_model = {
                'arango_id': video_path,
                'places': frames_model
            }

            # save
            output_path = None if not self.mgr.output_dir.get(msg) else os.path.join(
                self.mgr.output_dir.get(msg),
                os.path.splitext(os.path.basename(video_path))[0] + "out_places_detection"
            )
            self.save_detection(video_path,
                                places_model,
                                self.mgr.output_style.get(msg),
                                output_path)
            self.cur_task = None

            if self._exit_flag:
                break

    def save_detection(self, movie_id, places_model, output_style, output_path):
        """
        Save detection output in the desired format
        @param: movie_id: the movie id
        @param: movie_entity the movie's db entity
        @param: places_model: the places model
        @param: output_style: the saving method:
                    "json" - save as JSON to given `output_path`.
                    "anno" - not supported
                    "arango" - save as entry in arango DB.
        @param: output_path: local save path in case of "FILE" `output_style`.
        """
        try:
            if OUTPUT_STYLE_JSON in output_style:  # save as JSON
                with open(output_path + '.json', 'w') as f:
                    json.dump(places_model, f, indent=4)
                self.logger.info(f'successfully saved json annotation for {movie_id}')

            if OUTPUT_STYLE_ANNO in output_style:  # save as annotated video
                self.logger.info('no annotation in this places expert')
            #     PlacesAnnotator().annotate_video(video_path, preds, output_path, video_fps=fps, show_pbar=False)
            #     self.logger.info(f'successfully saved video annotation for {video_path}')

            if OUTPUT_STYLE_ARANGO in output_style:  # save as DB entry
                self.api.save_places_to_db(places_model)
                # nodes_saved = self.api.save_places_data_to_scene_graph(video_path, places_model)
                self.logger.info(f'successfully saved {movie_id} in DB')
        except Exception as e:
            self.logger.exception(f'received exception in save_detection: {e}')


class ArangoStep(ExpertPipelineStep):
    def run(self, q_in: Queue, q_out: AggQueue):
        self.logger.info('Arango client ready')

        self.mgr.logger.info('ready to receive remote commands')
        for movie_id in self.api.scheduler_loop():
            self.mgr.logger.info(f'got movie from scheduler: {movie_id}')
            q_out.put(self.mgr._get_video_msg(movie_id, is_remote=True))

