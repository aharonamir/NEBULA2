import sys
import os

sys.path.append("/workspaces/NEBULA2")
print(sys.path)
from nebula_api.nebula_enrichment_api import NRE_API
from experts.common.RemoteAPIUtility import RemoteAPIUtility
api = RemoteAPIUtility()
nre = NRE_API()
db = nre.db
print(nre.db_host)

from arango import ArangoClient
client = ArangoClient(hosts='http://ec2-18-158-123-0.eu-central-1.compute.amazonaws.com:8529')
dbname = 'nebula_development'
db_manual = client.db(dbname, username='nebula', password='nebula')
print(db_manual)

arango_id = "Movies/92354428"
movie_id = "f0a27202207444bd8bfb77708b0db3c5"

num_frames = api.downloadDirectoryFroms3(arango_id)
print(num_frames)

movie_info = api.get_movie_info(arango_id)
action_data = nre.get_all_expert_data("Actions", arango_id)
object_data = nre.get_all_expert_data("Object", arango_id)
clip_data = nre.get_clip_data(arango_id)
scenes = api.get_scenes(arango_id)

# get movie frames
for scene in scenes:
    scene_interaction = api.scene_intersection(scenes,scene['start'],scene['stop'])
    print(scene_interaction)

# get movie info from movie id
nebula_movies = []
query = f'FOR doc IN Movies FILTER doc.movie_id == "{movie_id}" RETURN doc'
cursor = db_manual.aql.execute(query)
for data in cursor:
    # print(data)
    nebula_movies.append(data)
print(nebula_movies)
movie = nebula_movies[0]



# movie_nodes = []
# query = f'FOR doc IN Nodes FILTER doc.movie_id == "{movie_id}" and doc.class == "Object" and not_null(doc.bboxes) RETURN doc'
# cursor = db_manual.aql.execute(query)
# # for data in cursor:
# #     # print(data)
# #     movie_nodes.append(data)
# # getting the first one
# test_node = not cursor.empty() and cursor.next() or None
# print(test_node)

