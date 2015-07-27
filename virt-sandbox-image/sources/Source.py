#!/usr/bin/python

from abc import ABCMeta, abstractmethod

class Source():
    __metaclass__ = ABCMeta
    def __init__(self):
        pass

    @abstractmethod
    def download_template(self,**args):
        pass

    @abstractmethod
    def create_template(self,**args):
      pass

    @abstractmethod
    def delete_template(self,**args):
      pass

    @abstractmethod
    def get_command(self,**args):
      pass

    def get_disk(self,**args):
      pass

    def get_volume(self,**args):
      pass
