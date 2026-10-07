import unittest
from pathlib import Path
from PIL import Image
from petting_visuals import PettingVisuals, hearts

class PettingVisualTests(unittest.TestCase):
    def test_complete_frames_have_fixed_height_and_ground(self):
        root=Path(__file__).resolve().parents[1]
        visuals=PettingVisuals(root/'assets/petting-smile')
        reference=Image.open(root/'assets/revamp/hq/idle/00.png').convert('RGBA')
        height=reference.getbbox()[3]-reference.getbbox()[1]
        self.assertEqual(len(visuals.hq),8)
        for frame in visuals.hq:
            bbox=frame.getbbox()
            self.assertEqual(frame.size,(384,544))
            self.assertLessEqual(abs((bbox[3]-bbox[1])-height),2)
            self.assertEqual(bbox[3],404)

    def test_hearts_animate_without_modifying_source(self):
        frame=Image.new('RGBA',(384,544))
        before=frame.tobytes()
        self.assertIsNone(hearts(frame,0).getbbox())
        first=hearts(frame,.5);second=hearts(frame,1.4)
        self.assertIsNotNone(first.getbbox())
        self.assertNotEqual(first.tobytes(),second.tobytes())
        self.assertEqual(frame.tobytes(),before)
        self.assertEqual(second.size,frame.size)

if __name__=='__main__':unittest.main()
