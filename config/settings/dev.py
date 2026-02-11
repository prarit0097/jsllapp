import os

from .base import *

DEBUG = os.getenv('DEBUG', 'true').lower() in {'1', 'true', 'yes'}