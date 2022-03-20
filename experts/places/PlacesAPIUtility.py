import os
import sys

# import from common
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.RemoteAPIUtility import RemoteAPIUtility

class PlacesAPIUtility(RemoteAPIUtility):
    def initialize(self):
        self.temp_file = "/tmp/places_video.mp4"

    def save_places_to_db(self, places_model):
        """
        save places model to database
        @param: movie_id the movie id (arango_id)
        @param: places_model the model to save
        """
        query = 'UPSERT { movie_id: @movie_id } INSERT \
            { movie_id: @movie_id, places: @places }\
                 UPDATE \
                { places: @places } IN Places \
                 RETURN { doc: NEW, type: OLD ? \'update\' : \'insert\' }'
        bind_vars = {
            'movie_id': places_model['arango_id'],
            'places': places_model['places'],
        }
        cursor = self.db.aql.execute(query, bind_vars=bind_vars)
        for doc in cursor:
            doc=doc
        return(doc['doc']['_id'])

    def scheduler_loop(self):
        """
        loops forever, waiting for movie tasks from arang.
        @return: yields movie arago ID's.
        """
        while True:
            # Signaling your code, that we have newly uploaded movie, frames are stored in S3.
            # Returns movie_id in form: Movie/<xxxxx>
            movies = self.nre.wait_for_change("Places", "ClipScene")
            for movie in movies:
                yield movie
            self.nre.update_expert_status("Places") #Update scheduler, set it to done status
