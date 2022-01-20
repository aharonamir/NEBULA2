import sys
import os

#sys.path.append("../")
from nebula_api.nebula_enrichment_api import NRE_API
nre = NRE_API()
db = nre.db
print(nre.db_host)

from arango import ArangoClient
client = ArangoClient(hosts='http://ec2-18-158-123-0.eu-central-1.compute.amazonaws.com:8529')
dbname = 'nebula_development'
db_manual = client.db(dbname, username='nebula', password='nebula')
print(db_manual)