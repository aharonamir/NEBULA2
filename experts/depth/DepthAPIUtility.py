import os
import sys
import cv2
import urllib.request

# import from common
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.RemoteAPIUtility import RemoteAPIUtility
# from nebula_api.scene_detector_api import NEBULA_SCENE_DETECTOR

class DepthAPIUtility(RemoteAPIUtility):
    def initialize(self):
        self.temp_file = "/tmp/depth_video.mp4"
        # self.scene_detector = NEBULA_SCENE_DETECTOR()
    def get_movie_meta(self, movie_id):
        nebula_movies={}

        query = 'FOR doc IN Movies FILTER doc._id == "{}"  RETURN doc'.format(movie_id)

        cursor = self.db.aql.execute(query)
        for data in cursor:
            nebula_movies[data['_id']] = data
        return(nebula_movies)

    def download_video_file(self, movie_id):
        if os.path.exists(self.temp_file):
            os.remove(self.temp_file)
        query = 'FOR doc IN Movies FILTER doc._id == "{}" RETURN doc'.format(movie_id)
        cursor = self.db.aql.execute(query)
        # url_prefix = "http://ec2-3-120-189-231.eu-central-1.compute.amazonaws.com:7000/"
        url_prefix = "http://ec2-18-159-140-240.eu-central-1.compute.amazonaws.com:7000/"
        url_link = ''
        for doc in cursor:
            url_link = url_prefix+doc['url_path']
            url_link = url_link.replace(".avi", ".mp4")
            print(url_link)
            urllib.request.urlretrieve(url_link, self.temp_file)
        return self.temp_file

    def divide_movie_into_frames(self, movie_in_path, movie_out_folder):
        cap = cv2.VideoCapture(movie_in_path)
        ret, frame = cap.read()
        num = 0
        cv2.imwrite(os.path.join(movie_out_folder, f'frame{num:04}.jpg'), frame)
        while cap.isOpened() and ret:
            num = num + 1
            ret, frame = cap.read()
            if frame is not None:
                cv2.imwrite(os.path.join(movie_out_folder,
                           f'frame{num:04}.jpg'), frame)
        return num
    # def create_action(self, arango_id, movie_id, frame_id, box, description, confidence, action_id):
    #     query = 'UPSERT { movie_id: @movie_id, arango_id: @arango_id, \
    #         action_id: @action_id}\
    #              INSERT  \
    #         { movie_id: @movie_id, arango_id: @arango_id, actor_id: @actor_id, description: @description, frame_id: @frame_id, \
    #             class: "Actions", confidence: @confidence, updates: 1, box: @box}\
    #              UPDATE \
    #             { updates: OLD.updates + 1, description: @description} IN Nodes \
    #                 RETURN { doc: NEW, type: OLD ? \'update\' : \'insert\' }'
    #     bind_vars = {
    #         'movie_id': movie_id,
    #         'arango_id': arango_id,
    #         'frame_id': frame_id,
    #         'actor_id': None,
    #         'box': box,
    #         'description': description,     # string name of action
    #         'confidence': confidence,
    #         'action_id': action_id
    #     }
    #     self.db.aql.execute(query, bind_vars=bind_vars)

    # def save_action_data_to_scene_graph(self, arango_id, actions_data):
    #     action_id = 0
    #     for frame_id, d in actions_data.items():
    #         for box, actions, scores in zip(d['detection_boxes'], d['detection_classes'], d['detection_scores']):
    #             for description, confidence in zip(actions, scores):
    #                 self.create_action(
    #                     arango_id=arango_id,
    #                     movie_id=self.get_movie_info(arango_id)['movie_id'],
    #                     frame_id=frame_id,
    #                     box=box,
    #                     description=description,
    #                     confidence=confidence,
    #                     action_id=action_id
    #                 )
    #                 action_id += 1

    def scheduler_loop(self):
        """
        loops forever, waiting for movie tasks from arang.
        @return: yields movie arago ID's.
        """
        while True:
            # Signaling your code, that we have newly uploaded movie, frames are stored in S3.
            # Returns movie_id in form: Movie/<xxxxx>
            movies = self.nre.wait_for_change("Depth", "ClipScene")
            for movie in movies:
                yield movie
            self.nre.update_expert_status("Depth") #Update scheduler, set it to done status
