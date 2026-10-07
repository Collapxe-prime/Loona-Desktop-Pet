"""Visual transition regressions for the installed whole-drawing animation repair."""
import json,unittest
from pathlib import Path
from PIL import Image
from main import pixel_bytes
from sprite_quality import radius_for

ROOT=Path(__file__).resolve().parents[1]/'assets/revamp'

class GreetingCheckTests(unittest.TestCase):
    def test_transition_frames_are_identical_to_idle_at_all_display_scales(self):
        manifest=json.loads((ROOT/'manifest.json').read_text())
        profile=json.loads((ROOT/'quality-profile.json').read_text())
        idle=Image.open(ROOT/'hq/idle/00.png').convert('RGBA')
        for name in ('waving','review'):
            indices=manifest['animations'][name]['idle_pose_frames']
            self.assertIn(31,indices)
            for i in indices:
                frame=Image.open(ROOT/'hq'/name/f'{i:02}.png').convert('RGBA')
                self.assertEqual(frame.tobytes(),idle.tobytes())
                for scale in (1,1.5,2):
                    quality=('matched',radius_for(profile,'idle',scale))
                    self.assertEqual(pixel_bytes(frame,scale/2,quality),pixel_bytes(idle,scale/2,quality))

    def test_duration_and_full_body_height_preserved(self):
        before=Path(__file__).parent/'fixtures/greeting-timings.json'
        old=json.loads(before.read_text());new=json.loads((ROOT/'manifest.json').read_text())
        for name in ('waving','review'):
            self.assertEqual(old[name],new['animations'][name]['durations_ms'])
            heights=[]
            for path in sorted((ROOT/'hq'/name).glob('*.png')):
                frame=Image.open(path).convert('RGBA');box=frame.getbbox()
                self.assertEqual(box[3],404);heights.append(box[3]-box[1])
            self.assertLessEqual(max(heights)-min(heights),1)

if __name__=='__main__':unittest.main()
