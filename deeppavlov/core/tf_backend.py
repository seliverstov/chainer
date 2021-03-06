import tensorflow as tf
from abc import ABCMeta
import functools
from functools import wraps
import types

from six import with_metaclass


def _graph_wrap(func, graph):
    @wraps(func)
    def _wrapped(*args, **kwargs):
        with graph.as_default():
            try:
                return func(*args, **kwargs)
            except TypeError:
                print("wrapped function is {}".format(func))
    return _wrapped


class TfModelMeta(with_metaclass(type, ABCMeta)):
    def __call__(cls, *args, **kwargs):
        if issubclass(cls, KerasModel):
            import keras.backend as K
            K.clear_session()

        obj = cls.__new__(cls)
        obj.graph = tf.Graph()
        for meth in dir(obj):
            if meth == '__class__':
                continue
            attr = getattr(obj, meth)
            # if callable(attr): # leads to an untraceable bug if an attribute
            # is initilaized via a class call, error doesn't raise
            # if isinstance(attr, (types.FunctionType, types.BuiltinFunctionType, functools.partial)):
            if callable(attr):
                setattr(obj, meth, _graph_wrap(attr, obj.graph))
        obj.__init__(*args, **kwargs)
        return obj


class TFModel(metaclass=TfModelMeta):
    pass


class KerasModel(metaclass=TfModelMeta):
    pass