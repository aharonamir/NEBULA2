import os
import sys
import warnings
import urllib.request

from arango import ArangoClient
import boto3

# import from nebula API
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from nebula_api.nebula_enrichment_api import NRE_API


class RemoteAPIUtility:
    """
    A utility class for communicating with DB and web services.
    """

    def __init__(self):
        """
        setup remote utility clients and tools.
        """
        self.download_bucket_name = "nebula-frames"
        self.s3 = boto3.client('s3', region_name='eu-central-1')
        self.nre = NRE_API()
        self.db = self.nre.db
        # self.client = ArangoClient(hosts='http://ec2-18-158-123-0.eu-central-1.compute.amazonaws.com:8529')
        # self.db = self.client.db("nebula_development", username='nebula', password='nebula')

    def get_movie_entity(self, entity_id):
        entity = None
        query = 'FOR doc IN Movies FILTER doc._id == "{}"  RETURN doc'.format(entity_id)
        cursor = self.db.aql.execute(query)
        for data in cursor:
            entity = data
            break # taking the first
        return (entity)

    def downloadDirectoryFroms3(self, arango_id):
        """
        Download a movie's directory of frames.
        @param: arango_id: movie ID including path, e.g. Movies/12345678
        @return: the number of downloaded frames
        """
        # prepare download bucket
        s3_resource = boto3.resource('s3')
        bucket = s3_resource.Bucket(self.download_bucket_name)

        # iterate download items
        keys = []
        for i, obj in enumerate(bucket.objects.filter(Prefix=arango_id)):
            if i == 0:
                continue  # first output is the directory
            keys.append(obj.key)

            if os.path.isfile(obj.key):  # frame already exists. skip download.
                continue

            if not os.path.exists(os.path.dirname(obj.key)):
                os.makedirs(os.path.dirname(obj.key))
            bucket.download_file(obj.key, obj.key)  # save to same path

        return len(keys)

    def downloadFilesFroms3(self, folder_name, file_names):
        """
        Download a list of files from a folder.
        @param: folder_name: files folder path, e.g. Movies/12345678
        @param: file_names: list of file names, e.g. frame0218.jpg
        @return: the number of downloaded files
        """
        # prepare download bucket
        s3_resource = boto3.resource('s3')
        bucket = s3_resource.Bucket(self.download_bucket_name)
        # prepare set of files
        file_names_set = set()
        for fname in file_names:
            file_names_set.add(f'{folder_name}/{fname}')

        # iterate download items
        files_downloaded = []
        for i, obj in enumerate(bucket.objects.filter(Prefix=folder_name)):
            if i == 0:
                continue  # first output is the directory
            if (obj.key not in file_names_set):
                continue

            files_downloaded.append(obj.key)

            if os.path.isfile(obj.key):  # frame already exists. skip download.
                continue

            if not os.path.exists(os.path.dirname(obj.key)):
                os.makedirs(os.path.dirname(obj.key))
            bucket.download_file(obj.key, obj.key)  # save to same path

        return len(files_downloaded)

    def get_movie_info(self, arango_id):
        """
        Get scenes for movie , you can find related scene element by comparing your start/stop and start/stop from database.
        @param: arango_id: movie ID including path, e.g. Movies/12345678
        """
        # query DB for all relevant scenes
        query = 'FOR doc IN Movies FILTER doc._id == "{}"  RETURN doc'.format(arango_id)
        cursor = self.db.aql.execute(query)

        # iterate DB output and save scenes info.
        all_infos = []
        for data in cursor:
            all_infos.append({
                'arango_id': data['_id'],            # same as param
                'description': data['description'],  # random identifier
                'fps': data['meta']['fps'],          # movie file metadata
                'width': data['meta']['width'],
                'height': data['meta']['height'],
                'last frame': data['last_frame'],
                'movie_id': data['movie_id'],        # random identifier
            })

        num_movies_found = len(all_infos)
        if num_movies_found > 1:
            warnings.warn(f'found several movies with id {arango_id}: {all_infos}')
        elif num_movies_found == 0:
            raise ValueError(f'No moveis found with id {arango_id}')

        return all_infos[0]

    def get_scenes(self, arango_id):
        """
        Get scenes for movie , you can find related scene element by comparing your start/stop and start/stop from database.
        @param: arango_id: movie ID including path, e.g. Movies/12345678
        """
        # query DB for all relevant scenes
        query = 'FOR doc IN StoryLine FILTER doc.arango_id == "{}"  RETURN doc'.format(arango_id)
        cursor = self.db.aql.execute(query)

        # iterate DB output and save scenes info.
        all_scenes = []
        for data in cursor:
            all_scenes.append({
                'scene_graph_triplets': data['scene_graph_triplets'],  # e.g. "horse is brown"
                'movie_id': data['movie_id'],                          # random identifier
                'arango_id': data['arango_id'],                        # same as param
                'description': data['description'],                    # scene description
                'scene_element': data['scene_element'],                # index of scene scene part
                'start': data['start'],                                # scene element start frame
                'stop': data['stop']                                   # scene element stop frame
            })

        return all_scenes

    def scene_intersection(self, scenes, obj_start, obj_stop):
        """
        find all scene elements that intersect with the object's presence.
        @param: scenes: a list of scene dictionaries gotten from the `get_scenes` function.
        @param: obj_start: The fame number of the first frame in which the object appears in this element.
        @param: obj_stop: The frame at which the object disappears in this scene element.
        @return: a list of tuples (scene, start, stop) where the scenes are those that intersect with the
                 current object in time, and start and stop are the latest starting frame and earliest
                 stopping frame of either the scene element or the object.
        """
        # intersection cases:
        # 1) scene_start <= obj_start <= scene_stop <= obj_stop  -----X---Y----X--Y--
        # 2) obj_start <= scene_start <= obj_stop <= scene_stop  --Y--X---Y----X-----
        # 3) scene_start <= obj_start <= obj_stop <= scene_stop  -----X---Y--Y-X-----
        # 4) obj_start <= scene_start <= scene_stop <= obj_stop  --Y--X--------X--Y--
        return [
            (scene,
             max(obj_start, scene['start']),  # intersection start
             min(obj_stop, scene['stop']))    # intersection end
            for scene in scenes
            if (scene['start'] <= obj_start <= scene['stop'] or  #  covers cases (1) and (3)
                scene['start'] <= obj_stop <= scene['stop']  or  #  covers case (2)
                (obj_start <= scene['start'] <= obj_stop) and (obj_start <= scene['stop'] <= obj_stop))  # (4)
        ]

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