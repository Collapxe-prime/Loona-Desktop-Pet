from pathlib import Path
import tempfile,unittest
from PIL import Image
from frame_cache import ByteLRU,LazyFrames
from build import BUILD
from revamp_loader import load_pack
from main import REVAMP_ROOT,REVAMP_PACK,pixel_bytes
from frame_registration import horizontal_register

class FrameCacheTests(unittest.TestCase):
    def test_byte_limit_lru_replacement_and_oversized_values(self):
        cache=ByteLRU(6,len)
        cache.put('a',b'aaa');cache.put('b',b'bbb')
        self.assertEqual(cache.get('a'),b'aaa')
        cache.put('c',b'ccc');self.assertIsNone(cache.get('b'))
        cache.put('a',b'a');self.assertEqual(cache.resident_bytes,4)
        cache.put('big',b'1234567');self.assertIsNone(cache.get('big'))
        self.assertLessEqual(cache.resident_bytes,6)
        cache.clear();self.assertEqual(cache.resident_bytes,0)

    def test_on_demand_frames_stay_byte_identical_after_eviction_and_registration(self):
        pack=load_pack(REVAMP_ROOT/'hq',REVAMP_PACK,canvas=(384,544),cache_bytes=384*544*4)
        cache=pack['idle'].cache
        self.assertEqual(cache.resident_bytes,0)
        for name in ('idle','jumping','waiting','walking-left','falling','look'):
            entry=REVAMP_PACK['animations'].get(name,{})
            for index in (0,len(pack[name])-1):
                with Image.open(REVAMP_ROOT/'hq'/name/f'{index:02}.png') as src:expected=src.copy()
                if entry.get('width_scales'):
                    expected=horizontal_register(expected,entry['width_scales'][index],entry['width_pivot_px']*2)
                actual=pack[name][index]
                self.assertEqual(actual.tobytes(),expected.tobytes())
                self.assertEqual(pixel_bytes(actual,.5),pixel_bytes(expected,.5))
                self.assertLessEqual(cache.resident_bytes,cache.max_bytes)
        before=pack['idle'][0].tobytes()
        pack['falling'][-1]
        self.assertEqual(pack['idle'][0].tobytes(),before)
        with self.assertRaises(IndexError):pack['idle'][len(pack['idle'])]

    def test_invalid_header_fails_without_decoding_whole_pack(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as directory:
            file=Path(directory)/'invalid.png';Image.new('RGB',(2,2)).save(file)
            with self.assertRaises(ValueError):LazyFrames([file],(2,2),ByteLRU(16,len))

if __name__=='__main__':unittest.main()
