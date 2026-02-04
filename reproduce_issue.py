
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import os

# Mock onnxruntime before importing onnx_asr
sys.modules["onnxruntime"] = MagicMock()

import onnx_asr
# onnx_asr.models.nemo imports onnxruntime as rt, so we need to make sure it uses our mock
from onnx_asr.loader import load_model

class TestModelLoading(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("temp_models/test-model-int8")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        # Create dummy files
        (self.test_dir / "encoder-model.onnx").touch()
        (self.test_dir / "encoder-model.int8.onnx").touch()
        (self.test_dir / "decoder_joint-model.onnx").touch()
        (self.test_dir / "decoder_joint-model.int8.onnx").touch()
        
        # Write valid vocab
        with (self.test_dir / "vocab.txt").open("w") as f:
            f.write("<blk> 0\n")
            f.write("a 1\n")
            f.write("b 2\n")

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree("temp_models")

    def test_load_int8(self):
        with patch("onnxruntime.InferenceSession") as mock_session:
            print(f"Testing load_model with quantization='int8' in {self.test_dir}")
            
            # We use a known model name that maps to NemoConformerTdt
            model_name = "nemo-parakeet-tdt-0.6b-v3"
            
            try:
                model = load_model(
                    model_name,
                    path=str(self.test_dir),
                    quantization="int8"
                )
            except Exception as e:
                print(f"Caught exception: {e}")
                raise

            # Check calls to InferenceSession
            found_int8_encoder = False
            found_int8_decoder = False
            
            for call in mock_session.call_args_list:
                args, _ = call
                filepath = str(args[0])
                print(f"InferenceSession called with: {filepath}")
                if "encoder-model.int8.onnx" in filepath:
                    found_int8_encoder = True
                if "decoder_joint-model.int8.onnx" in filepath:
                    found_int8_decoder = True
                    
            if found_int8_encoder and found_int8_decoder:
                print("SUCCESS: Loaded int8 files")
            else:
                print("FAILURE: Did not load int8 files")
                self.fail("Did not load int8 files")

if __name__ == "__main__":
    unittest.main()
