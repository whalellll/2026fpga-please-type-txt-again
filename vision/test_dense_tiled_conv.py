"""Acceptance tests for convolution through the existing dense S8S8 ABI."""
import random
import struct
import time
import unittest

from dense_tiled_conv import ConvSpec, dense_reference, make_jobs, run_tiled


def matrix_backend(job):
    result = []
    ci_tiles = (job.k + 3) // 4
    for p in range(job.pixels):
        for co in range(job.cout):
            total = 0
            for k in range(job.k):
                a = struct.unpack_from('<h', job.inputs, (p * ci_tiles * 4 + k) * 2)[0]
                address = ((co // 32 * ci_tiles + k // 4) * 128 +
                           (co % 32 // 2 * 4 + k % 4) * 2 + co % 2)
                b = struct.unpack_from('b', job.weights, address)[0]
                total += a * b
            result.append(total)
    return result


class DenseTiledConvTests(unittest.TestCase):
    def data(self, spec):
        rng = random.Random(7)
        x = bytes(rng.randrange(256) for _ in range(spec.width * spec.height * spec.cin))
        w = bytes(rng.randrange(256) for _ in range(spec.cout * spec.cin * spec.kernel**2))
        return x, w

    def test_stride_padding_and_first_kernel6(self):
        for spec in (ConvSpec(5, 4, 5, 7, 3, 2, 1), ConvSpec(8, 8, 3, 16, 6, 2, 2)):
            x, w = self.data(spec)
            bias = [i - 9 for i in range(spec.cout)]
            result = run_tiled(spec, x, w, bias, 10, matrix_backend)
            self.assertEqual(result['int32'], dense_reference(spec, x, w, bias))

    def test_k1152_and_57_output_tail_exact(self):
        spec = ConvSpec(3, 3, 128, 57, 3, 1, 0)
        x, w = self.data(spec)
        jobs = list(make_jobs(spec, x, w))
        self.assertEqual([j.k for j in jobs], [256, 256, 256, 256, 128])
        self.assertEqual(len(jobs[0].weights), 2 * 64 * 128)
        result = run_tiled(spec, x, w, [0]*57, 12, matrix_backend)
        self.assertEqual(result['int32'], dense_reference(spec, x, w, [0]*57))

    def test_partial_sums_must_not_saturate_before_accumulation(self):
        spec = ConvSpec(1, 1, 512, 1, 1, 1, 0)
        result = run_tiled(spec, bytes([127]*512), bytes([127]*256+[129]*256),
                           [3], 0, matrix_backend)
        self.assertEqual(result['int32'], [3])
        self.assertEqual(result['s8'], bytes([3]))

    def test_pixel_and_output_channel_chunks_and_signed_packing(self):
        spec = ConvSpec(17, 1, 5, 257, 1, 1, 0)
        x, w = self.data(spec)
        result = run_tiled(spec, x, w, [0]*257, 10, matrix_backend)
        self.assertEqual(result['jobs'], 4)
        self.assertEqual(result['int32'], dense_reference(spec, x, w, [0]*257))
        spec = ConvSpec(1, 1, 5, 33, 1, 1, 0)
        x = bytes([128, 127, 255, 0, 1])
        w = bytes((i % 251 for i in range(33*5)))
        job = next(make_jobs(spec, x, w))
        self.assertEqual(struct.unpack('<8h', job.inputs), (-128, 127, -1, 0, 1, 0, 0, 0))
        self.assertEqual(job.weights[0], w[0])
        self.assertEqual(job.weights[1], w[5])
        self.assertEqual(job.weights[128], w[4])
        self.assertEqual(job.weights[256], w[160])
        self.assertEqual(job.weights[257], 0)

    def test_invalid_buffers_geometry_bias_and_backend_failure(self):
        with self.assertRaises(ValueError): ConvSpec(0, 1, 1, 1, 1, 1, 0)
        spec = ConvSpec(1, 1, 1, 1, 1, 1, 0)
        with self.assertRaises(ValueError): list(make_jobs(spec, b'', b'\1'))
        with self.assertRaises(ValueError): run_tiled(spec, b'\1', b'\1', [2**31], 0, matrix_backend)
        def failed(job): raise RuntimeError('hardware timeout')
        with self.assertRaises(RuntimeError): run_tiled(spec, b'\1', b'\1', [0], 0, failed)

    def test_maximum_job_capacity_and_measured_packing(self):
        spec = ConvSpec(4, 4, 256, 256, 1, 1, 0)
        x, w = self.data(spec)
        started = time.perf_counter()
        jobs = list(make_jobs(spec, x, w))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(jobs[0].inputs)+len(jobs[0].weights)+jobs[0].pixels*jobs[0].cout*4, 90112)
        print('DENSE_TILED_PACK_PERF jobs=1 bytes=90112 elapsed_ms=%.3f' % ((time.perf_counter()-started)*1000))


if __name__ == '__main__':
    unittest.main()
