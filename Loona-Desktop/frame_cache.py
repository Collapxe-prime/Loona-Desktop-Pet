"""Bounded LRU storage and on-demand decoding; no animation frames are removed."""
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from PIL import Image

class ByteLRU:
    def __init__(self,max_bytes,size_of):
        if max_bytes<0:raise ValueError('Negative cache budget')
        self.max_bytes=max_bytes;self.size_of=size_of
        self.items=OrderedDict();self.resident_bytes=0

    def get(self,key):
        entry=self.items.get(key)
        if entry is None:return None
        self.items.move_to_end(key)
        return entry[0]

    def put(self,key,value):
        old=self.items.pop(key,None)
        if old:self.resident_bytes-=old[1]
        cost=self.size_of(value)
        if cost>self.max_bytes:return
        while self.items and self.resident_bytes+cost>self.max_bytes:
            _,entry=self.items.popitem(last=False)
            self.resident_bytes-=entry[1]
        self.items[key]=(value,cost);self.resident_bytes+=cost

    def clear(self):
        self.items.clear();self.resident_bytes=0

    def __len__(self):return len(self.items)

class LazyFrames(Sequence):
    def __init__(self,paths,canvas,cache,factors=None,pivot=0):
        self.paths=tuple(Path(p) for p in paths);self.canvas=canvas;self.cache=cache
        self.factors=factors;self.pivot=pivot
        # Headers are cheap; leave compressed pixel data on disk until needed.
        for path in self.paths:
            with Image.open(path) as source:
                if source.size!=canvas or source.mode!='RGBA':
                    raise ValueError(f'Invalid RGBA sprite: {path}')

    def __len__(self):return len(self.paths)

    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self)))]
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        factor=self.factors[index] if self.factors else 1
        key=(self.paths[index],factor,self.pivot)
        frame=self.cache.get(key)
        if frame is None:
            with Image.open(self.paths[index]) as source:frame=source.copy()
            if not frame.getbbox():raise ValueError(f'Empty sprite: {self.paths[index]}')
            if abs(factor-1)>1e-9:
                from frame_registration import horizontal_register
                frame=horizontal_register(frame,factor,self.pivot)
            self.cache.put(key,frame)
        return frame
