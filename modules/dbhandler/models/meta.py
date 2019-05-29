"""The declarative_base object must be imported in a DB map file to get the
metadata of the DB. The same object must be used in the dbhandler when creating
session and engine to pass that metadata. Therefore, it needs to be handled in
a seperate file to avoid circular import at least when using SQlite. It works
with mySQL but its a rather messy solution."""
from sqlalchemy.ext.declarative import declarative_base

BASE = declarative_base()
