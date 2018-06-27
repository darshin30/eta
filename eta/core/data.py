'''
Core data structures for representing data and containers of data.

Copyright 2017-2018, Voxel51, LLC
voxel51.com

Brian Moore, brian@voxel51.com
Jason Corso, jason@voxel51.com
'''
# pragma pylint: disable=redefined-builtin
# pragma pylint: disable=unused-wildcard-import
# pragma pylint: disable=wildcard-import
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from builtins import *
# pragma pylint: enable=redefined-builtin
# pragma pylint: enable=unused-wildcard-import
# pragma pylint: enable=wildcard-import


from eta.core.geometry import RelativePoint
from eta.core.serial import Serializable


class DataContainer(Serializable):
    '''Base class for containers that store lists of data instances.

    This class should not be instantiated directly. Instead a subclass should
    be created for each type of data to be stored.

    Attributes:
        data: a list of instances of data of a specific class
    '''

    # The class of the data stored in the container
    _DATA_CLS = None

    def __init__(self, data=None):
        '''Constructs a DataContainer.

        Args:
            data: optional list of data instances to store.
        '''
        self._validate()
        self.data = data or []

    def __iter__(self):
        return iter(self.data)

    @classmethod
    def get_data_class(cls):
        '''Gets the class of data instances stored in this container.'''
        return cls._DATA_CLS

    @property
    def num(self):
        '''The number of data instances in the container.'''
        return len(self.data)

    def add(self, instance):
        '''Adds a data instance to the container.

        Args:
            instance: an instance for this container
        '''
        self.data.append(instance)

    def get_matches(self, filters, match=any):
        '''Returns a data container containing only instances that match the
        filters.

        Args:
            filters: a list of functions that accept data instances and return
                True/False
            match: a function (usually `any` or `all`) that accepts an iterable
                and returns True/False. Used to aggregate the outputs of each
                filter to decide whether a match has occurred. The default is
                `any`
        '''
        return self.__class__(
            data=list(filter(
                lambda o: match(f(o) for f in filters),
                self.data,
            )),
        )

    def count_matches(self, filters, match=any):
        '''Counts number of data instances that match the filters.

        Args:
            filters: a list of functions that accept data instances and return
                True/False
            match: a function (usually `any` or `all`) that accepts an iterable
                and returns True/False. Used to aggregate the outputs of each
                filter to decide whether a match has occurred. The default is
                `any`
        '''
        return len(self.get_matches(filters, match=match).data)

    @classmethod
    def from_dict(cls, d):
        '''Constructs an DataContainer from a JSON dictionary.'''
        cls._validate()
        return cls(data=[cls._DATA_CLS.from_dict(do) for do in d["data"]])

    @classmethod
    def _validate(cls):
        if cls._DATA_CLS is None:
            raise ValueError(
                "_DATA_CLS is None; note that you cannot instantiate "
                "DataContainer directly."
            )


class NamedRelativePoint(Serializable):
    '''A relative point that also has a label.

    Attributes:
        label: object label
        relative_point: a RelativePoint instance
    '''

    def __init__(self, label, relative_point):
        '''Constructs a NamedRelativePoint.

        Args:
            label: label string
            relative_point: a RelativePoint instance
        '''
        self.label = str(label)
        self.relative_point = relative_point

    @classmethod
    def from_dict(cls, d):
        '''Constructs a NamedRelativePoint from a JSON dictionary.'''
        return cls(
            d["label"],
            RelativePoint.from_dict(d["relative_point"]),
        )


class LocalizedTags(DataContainer):
    '''Container for points in an image or frame that each have a label
    associated with them (tags).'''

    _DATA_CLS = NamedRelativePoint

    def label_set(self):
        '''Returns a set containing the labels of the NamedRelativePoints.'''
        return set(dat.label for dat in self.data)