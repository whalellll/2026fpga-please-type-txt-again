import unittest
import numpy as np
from weight_quantization import quantize_per_output_channel, dequantize


class WeightQuantizationTests(unittest.TestCase):
    def test_independent_channel_scales_and_even_rounding(self):
        w=np.array([[-1,-.5,.5,1],[-2,-.25,.25,2]],dtype=np.float32).reshape(2,1,1,4)
        q,s=quantize_per_output_channel(w,4)
        np.testing.assert_array_equal(q.reshape(2,4),[[-7,-4,4,7],[-7,-1,1,7]])
        np.testing.assert_allclose(s.reshape(2),[1/7,2/7],rtol=1e-14)
        np.testing.assert_allclose(dequantize(q,s).reshape(2,4),
                                   [[-1,-4/7,4/7,1],[-2,-2/7,2/7,2]],rtol=1e-6)
        q8,s8=quantize_per_output_channel(w[:1],8)
        np.testing.assert_array_equal(q8.reshape(4),[-127,-64,64,127])
        self.assertEqual(q8.dtype,np.int8)
        self.assertEqual(dequantize(q8,s8).dtype,np.float32)

    def test_zero_channel_and_error_bound(self):
        rng=np.random.default_rng(42)
        w=rng.normal(size=(7,5,3,3)).astype(np.float32)
        w[0]=0
        for bits in (4,8):
            q,s=quantize_per_output_channel(w,bits)
            self.assertEqual(s[0,0,0,0],1)
            np.testing.assert_array_equal(q[0],0)
            self.assertTrue(np.all(np.abs(dequantize(q,s)-w)<=s/2+1e-6))
            self.assertTrue(np.max(np.abs(q))<2**(bits-1))

    def test_invalid_weights_and_precision_fail(self):
        for w,bits in [(np.zeros((1,1,1,1)),3),(np.zeros((1,2)),4),
                       (np.zeros((0,1,1,1)),8),(np.full((1,1,1,1),np.nan),4),
                       (np.full((1,1,1,1),np.inf),8)]:
            with self.assertRaises(ValueError): quantize_per_output_channel(w,bits)

    def test_float32_tiny_weights_remain_finite(self):
        w=np.array([np.nextafter(np.float32(0),np.float32(1))],dtype=np.float32).reshape(1,1,1,1)
        q,s=quantize_per_output_channel(w,8)
        self.assertEqual(q.item(),127)
        self.assertGreater(s.item(),0)
        np.testing.assert_array_equal(dequantize(q,s),w)


if __name__=='__main__': unittest.main()
