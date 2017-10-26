import json
import random
import types
import unittest

import numpy

from smqtk.algorithms.nn_index.lsh import LSHNearestNeighborIndex
from smqtk.algorithms.nn_index.lsh.functors import LshFunctor
from smqtk.algorithms.nn_index.lsh.functors.itq import ItqFunctor
from smqtk.algorithms.nn_index.hash_index.linear import LinearHashIndex
from smqtk.algorithms.nn_index.hash_index.sklearn_balltree import \
    SkLearnBallTreeHashIndex
from smqtk.exceptions import ReadOnlyError
from smqtk.representation.descriptor_element.local_elements import \
    DescriptorMemoryElement
from smqtk.representation.descriptor_index.memory import MemoryDescriptorIndex
from smqtk.representation.key_value.memory import MemoryKeyValueStore


class DummyHashFunctor (LshFunctor):

    @classmethod
    def is_usable(cls):
        return True

    def get_config(self):
        return {}

    def get_hash(self, descriptor):
        return numpy.zeros(8, bool)


class TestLshIndex (unittest.TestCase):

    def test_is_usable(self):
        # Should always be usable since this is a shell class.
        self.assertTrue(LSHNearestNeighborIndex.is_usable())

    def test_configuration(self):
        c = LSHNearestNeighborIndex.get_default_config()

        # Check that default is in JSON format and is decoded to the same
        # result.
        self.assertEqual(json.loads(json.dumps(c)), c)

        # Make a simple configuration
        # - ItqFunctor should always be available since it has no dependencies.
        c['lsh_functor']['type'] = 'ItqFunctor'
        c['descriptor_index']['type'] = 'MemoryDescriptorIndex'
        c['hash2uuids_kvstore']['type'] = 'MemoryKeyValueStore'
        c['hash_index']['type'] = 'LinearHashIndex'
        index = LSHNearestNeighborIndex.from_config(c)

        self.assertIsInstance(index.lsh_functor, ItqFunctor)
        self.assertIsInstance(index.descriptor_index, MemoryDescriptorIndex)
        self.assertIsInstance(index.hash_index, LinearHashIndex)
        self.assertIsInstance(index.hash2uuids_kvstore, MemoryKeyValueStore)

        # Can convert instance config to JSON
        self.assertEqual(
            json.loads(json.dumps(index.get_config())),
            index.get_config()
        )

    def test_configuration_none_HI(self):
        c = LSHNearestNeighborIndex.get_default_config()

        # Check that default is in JSON format and is decoded to the same
        # result.
        self.assertEqual(json.loads(json.dumps(c)), c)

        # Make a simple configuration
        c['lsh_functor']['type'] = 'ItqFunctor'
        c['descriptor_index']['type'] = 'MemoryDescriptorIndex'
        c['hash2uuids_kvstore']['type'] = 'MemoryKeyValueStore'
        c['hash_index']['type'] = None
        index = LSHNearestNeighborIndex.from_config(c)

        self.assertIsInstance(index.lsh_functor, ItqFunctor)
        self.assertIsInstance(index.descriptor_index, MemoryDescriptorIndex)
        self.assertIsNone(index.hash_index)
        self.assertIsInstance(index.hash2uuids_kvstore, MemoryKeyValueStore)

        # Can convert instance config to JSON
        self.assertEqual(
            json.loads(json.dumps(index.get_config())),
            index.get_config()
        )

    def test_get_dist_func_euclidean(self):
        f = LSHNearestNeighborIndex._get_dist_func('euclidean')
        self.assertIsInstance(f, types.FunctionType)
        self.assertAlmostEqual(
            f(numpy.array([0, 0]), numpy.array([0, 1])),
            1.0
        )

    def test_get_dist_func_cosine(self):
        f = LSHNearestNeighborIndex._get_dist_func('cosine')
        self.assertIsInstance(f, types.FunctionType)
        self.assertAlmostEqual(
            f(numpy.array([1, 0]), numpy.array([0, 1])),
            1.0
        )
        self.assertAlmostEqual(
            f(numpy.array([1, 0]), numpy.array([1, 1])),
            0.5
        )

    def test_get_dist_func_hik(self):
        f = LSHNearestNeighborIndex._get_dist_func('hik')
        self.assertIsInstance(f, types.FunctionType)
        self.assertAlmostEqual(
            f(numpy.array([0, 0]), numpy.array([0, 1])),
            1.0
        )
        self.assertAlmostEqual(
            f(numpy.array([1, 0]), numpy.array([0, 1])),
            1.0
        )
        self.assertAlmostEqual(
            f(numpy.array([1, 1]), numpy.array([0, 1])),
            0.0
        )

    def test_build_index_read_only(self):
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        MemoryDescriptorIndex(),
                                        MemoryKeyValueStore(), read_only=True)
        self.assertRaises(
            ReadOnlyError,
            index.build_index, []
        )

    def test_build_index_no_descriptors(self):
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        MemoryDescriptorIndex(),
                                        MemoryKeyValueStore(), read_only=False)
        self.assertRaises(
            ValueError,
            index.build_index, []
        )

    def test_build_index_fresh_build(self):
        descr_index = MemoryDescriptorIndex()
        hash_kvs = MemoryKeyValueStore()
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        descr_index, hash_kvs)

        descriptors = [
            DescriptorMemoryElement('t', 0),
            DescriptorMemoryElement('t', 1),
            DescriptorMemoryElement('t', 2),
            DescriptorMemoryElement('t', 3),
            DescriptorMemoryElement('t', 4),
        ]
        for i, d in enumerate(descriptors):
            d.set_vector(numpy.ones(8, float) * i)
        index.build_index(descriptors)

        # Make sure descriptors are now in attached index and in key-value-store
        self.assertEqual(descr_index.count(), 5)
        for d in descriptors:
            self.assertIn(d, descr_index)
        # Dummy hash functor always returns the same hash (0), so there should
        # only be one key (0) in KVS that contains all descriptor UUIDs.
        self.assertEqual(hash_kvs.count(), 1)
        self.assertSetEqual(hash_kvs.get(0), set(d.uuid() for d in descriptors))

    def test_build_index_fresh_build_with_hash_index(self):
        descr_index = MemoryDescriptorIndex()
        hash_kvs = MemoryKeyValueStore()
        linear_hi = LinearHashIndex()  # simplest hash index, heap-sorts.
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        descr_index, hash_kvs, linear_hi)

        descriptors = [
            DescriptorMemoryElement('t', 0),
            DescriptorMemoryElement('t', 1),
            DescriptorMemoryElement('t', 2),
            DescriptorMemoryElement('t', 3),
            DescriptorMemoryElement('t', 4),
        ]
        for i, d in enumerate(descriptors):
            d.set_vector(numpy.ones(8, float) * i)
        index.build_index(descriptors)

        # Make sure descriptors are now in attached index and in key-value-store
        # - This block is the same as ``test_build_index_fresh_build``
        self.assertEqual(descr_index.count(), 5)
        for d in descriptors:
            self.assertIn(d, descr_index)
        # Dummy hash functor always returns the same hash (0), so there should
        # only be one key (0) in KVS that contains all descriptor UUIDs.
        self.assertEqual(hash_kvs.count(), 1)
        self.assertSetEqual(hash_kvs.get(0), set(d.uuid() for d in descriptors))

        # hash index should have been built with hash vectors, or 0 in our case.
        self.assertEqual(linear_hi.index, {0})

    def test_update_index_read_only(self):
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        MemoryDescriptorIndex(),
                                        MemoryKeyValueStore(), read_only=True)
        self.assertRaises(
            ReadOnlyError,
            index.update_index, []
        )

    def test_update_index_no_descriptors(self):
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        MemoryDescriptorIndex(),
                                        MemoryKeyValueStore(), read_only=False)
        self.assertRaises(
            ValueError,
            index.update_index, []
        )

    def test_update_index_no_existing_index(self):
        # Test that calling update_index with no existing index acts like
        # building the index fresh.  This test is basically the same as
        # test_build_index_fresh_build but using update_index instead.
        descr_index = MemoryDescriptorIndex()
        hash_kvs = MemoryKeyValueStore()
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        descr_index, hash_kvs)

        descriptors = [
            DescriptorMemoryElement('t', 0),
            DescriptorMemoryElement('t', 1),
            DescriptorMemoryElement('t', 2),
            DescriptorMemoryElement('t', 3),
            DescriptorMemoryElement('t', 4),
        ]
        for d in descriptors:
            d.set_vector(numpy.ones(8, float) * d.uuid())
        index.update_index(descriptors)

        # Make sure descriptors are now in attached index and in key-value-store
        self.assertEqual(descr_index.count(), 5)
        for d in descriptors:
            self.assertIn(d, descr_index)
        # Dummy hash functor always returns the same hash (0), so there should
        # only be one key (0) in KVS that contains all descriptor UUIDs.
        self.assertEqual(hash_kvs.count(), 1)
        self.assertSetEqual(hash_kvs.get(0), set(d.uuid() for d in descriptors))

    def test_update_index_add_new_descriptors(self):
        # Test that calling update index after a build index causes index
        # components to be properly updated.
        descr_index = MemoryDescriptorIndex()
        hash_kvs = MemoryKeyValueStore()
        index = LSHNearestNeighborIndex(DummyHashFunctor(),
                                        descr_index, hash_kvs)
        descriptors1 = [
            DescriptorMemoryElement('t', 0),
            DescriptorMemoryElement('t', 1),
            DescriptorMemoryElement('t', 2),
            DescriptorMemoryElement('t', 3),
            DescriptorMemoryElement('t', 4),
        ]
        descriptors2 = [
            DescriptorMemoryElement('t', 5),
            DescriptorMemoryElement('t', 6),
        ]
        for d in descriptors1 + descriptors2:
            d.set_vector(numpy.ones(8, float) * d.uuid())

        # Build initial index.
        index.build_index(descriptors1)
        self.assertEqual(descr_index.count(), 5)
        for d in descriptors1:
            self.assertIn(d, descr_index)
        for d in descriptors2:
            self.assertNotIn(d, descr_index)
        self.assertEqual(hash_kvs.count(), 1)
        self.assertSetEqual(hash_kvs.get(0),
                            set(d.uuid() for d in descriptors1))

        # Update index and check that components have new data.
        index.update_index(descriptors2)
        self.assertEqual(descr_index.count(), 7)
        for d in descriptors1 + descriptors2:
            self.assertIn(d, descr_index)
        self.assertEqual(hash_kvs.count(), 1)
        self.assertSetEqual(hash_kvs.get(0),
                            set(d.uuid() for d in descriptors1 + descriptors2))


class TestLshIndexAlgorithms (unittest.TestCase):
    """
    Various tests on the ``nn`` method for different inputs and parameters.
    """

    RANDOM_SEED = 0

    def _make_ftor_itq(self, bits=32):
        itq_ftor = ItqFunctor(bit_length=bits, random_seed=self.RANDOM_SEED)

        def itq_fit(D):
            itq_ftor.fit(D)

        return itq_ftor, itq_fit

    def _make_hi_linear(self):
        return LinearHashIndex()

    def _make_hi_balltree(self):
        return SkLearnBallTreeHashIndex(random_seed=self.RANDOM_SEED)

    #
    # Test LSH with random vectors
    #
    def _random_euclidean(self, hash_ftor, hash_idx,
                          ftor_train_hook=lambda d: None):
        # :param hash_ftor: Hash function class for generating hash codes for
        #   descriptors.
        # :param hash_idx: Hash index instance to use in local LSH algo
        #   instance.
        # :param ftor_train_hook: Function for training functor if necessary.

        # make random descriptors
        i = 1000
        dim = 256
        td = []
        numpy.random.seed(self.RANDOM_SEED)
        for j in range(i):
            d = DescriptorMemoryElement('random', j)
            d.set_vector(numpy.random.rand(dim))
            td.append(d)

        ftor_train_hook(td)

        di = MemoryDescriptorIndex()
        kvstore = MemoryKeyValueStore()
        index = LSHNearestNeighborIndex(hash_ftor, di, kvstore,
                                        hash_index=hash_idx,
                                        distance_method='euclidean')
        index.build_index(td)

        # test query from build set -- should return same descriptor when k=1
        q = td[255]
        r, dists = index.nn(q, 1)
        self.assertEqual(r[0], q)

        # test query very near a build vector
        td_q = td[0]
        q = DescriptorMemoryElement('query', i)
        v = td_q.vector().copy()
        v_min = max(v.min(), 0.1)
        v[0] += v_min
        v[dim-1] -= v_min
        q.set_vector(v)
        r, dists = index.nn(q, 1)
        self.assertFalse(numpy.array_equal(q.vector(), td_q.vector()))
        self.assertEqual(r[0], td_q)

        # random query
        q = DescriptorMemoryElement('query', i+1)
        q.set_vector(numpy.random.rand(dim))

        # for any query of size k, results should at least be in distance order
        r, dists = index.nn(q, 10)
        for j in range(1, len(dists)):
            self.assertGreater(dists[j], dists[j-1])
        r, dists = index.nn(q, i)
        for j in range(1, len(dists)):
            self.assertGreater(dists[j], dists[j-1])

    def test_random_euclidean__itq__None(self):
        ftor, fit = self._make_ftor_itq()
        self._random_euclidean(ftor, None, fit)

    def test_random_euclidean__itq__linear(self):
        ftor, fit = self._make_ftor_itq()
        hi = self._make_hi_linear()
        self._random_euclidean(ftor, hi, fit)

    def test_random_euclidean__itq__balltree(self):
        ftor, fit = self._make_ftor_itq()
        hi = self._make_hi_balltree()
        self._random_euclidean(ftor, hi, fit)

    #
    # Test unit vectors
    #
    def _known_unit(self, hash_ftor, hash_idx, dist_method,
                    ftor_train_hook=lambda d: None):
        ###
        # Unit vectors - Equal distance
        #
        dim = 5
        test_descriptors = []
        for i in range(dim):
            v = numpy.zeros(dim, float)
            v[i] = 1.
            d = DescriptorMemoryElement('unit', i)
            d.set_vector(v)
            test_descriptors.append(d)

        ftor_train_hook(test_descriptors)

        di = MemoryDescriptorIndex()
        kvstore = MemoryKeyValueStore()
        index = LSHNearestNeighborIndex(hash_ftor, di, kvstore,
                                        hash_index=hash_idx,
                                        distance_method=dist_method)
        index.build_index(test_descriptors)

        # query with zero vector
        # -> all modeled descriptors have no intersection, dists should be 1.0,
        #    or maximum distance by histogram intersection
        q = DescriptorMemoryElement('query', 0)
        q.set_vector(numpy.zeros(dim, float))
        r, dists = index.nn(q, dim)
        # All dists should be 1.0, r order doesn't matter
        for d in dists:
            self.assertEqual(d, 1.)

        # query with index element
        q = test_descriptors[3]
        r, dists = index.nn(q, 1)
        self.assertEqual(r[0], q)
        self.assertEqual(dists[0], 0.)

        r, dists = index.nn(q, dim)
        self.assertEqual(r[0], q)
        self.assertEqual(dists[0], 0.)

    def test_known_unit__euclidean__itq__None(self):
        ftor, fit = self._make_ftor_itq(5)
        self._known_unit(ftor, None, 'euclidean', fit)

    def test_known_unit__hik__itq__None(self):
        ftor, fit = self._make_ftor_itq(5)
        self._known_unit(ftor, None, 'hik', fit)

    def test_known_unit__euclidean__itq__linear(self):
        ftor, fit = self._make_ftor_itq(5)
        hi = self._make_hi_linear()
        self._known_unit(ftor, hi, 'euclidean', fit)

    def test_known_unit__hik__itq__linear(self):
        ftor, fit = self._make_ftor_itq(5)
        hi = self._make_hi_linear()
        self._known_unit(ftor, hi, 'hik', fit)

    def test_known_unit__euclidean__itq__balltree(self):
        ftor, fit = self._make_ftor_itq(5)
        hi = self._make_hi_balltree()
        self._known_unit(ftor, hi, 'euclidean', fit)

    def test_known_unit__hik__itq__balltree(self):
        ftor, fit = self._make_ftor_itq(5)
        hi = self._make_hi_balltree()
        self._known_unit(ftor, hi, 'hik', fit)

    #
    # Test with known vectors and euclidean dist
    #
    def _known_ordered_euclidean(self, hash_ftor, hash_idx,
                                 ftor_train_hook=lambda d: None):
        # make vectors to return in a known euclidean distance order
        i = 1000
        test_descriptors = []
        for j in range(i):
            d = DescriptorMemoryElement('ordered', j)
            d.set_vector(numpy.array([j, j*2], float))
            test_descriptors.append(d)
        random.shuffle(test_descriptors)

        ftor_train_hook(test_descriptors)

        di = MemoryDescriptorIndex()
        kvstore = MemoryKeyValueStore()
        index = LSHNearestNeighborIndex(hash_ftor, di, kvstore,
                                        hash_index=hash_idx,
                                        distance_method='euclidean')
        index.build_index(test_descriptors)

        # Since descriptors were built in increasing distance from (0,0),
        # returned descriptors for a query of [0,0] should be in index order.
        q = DescriptorMemoryElement('query', i)
        q.set_vector(numpy.array([0, 0], float))
        # top result should have UUID == 0 (nearest to query)
        r, dists = index.nn(q, 5)
        self.assertEqual(r[0].uuid(), 0)
        self.assertEqual(r[1].uuid(), 1)
        self.assertEqual(r[2].uuid(), 2)
        self.assertEqual(r[3].uuid(), 3)
        self.assertEqual(r[4].uuid(), 4)
        # global search should be in complete order
        r, dists = index.nn(q, i)
        for j, d, dist in zip(range(i), r, dists):
            self.assertEqual(d.uuid(), j)

    def test_known_ordered_euclidean__itq__None(self):
        ftor, fit = self._make_ftor_itq(1)
        self._known_ordered_euclidean(ftor, None, fit)

    def test_known_ordered_euclidean__itq__linear(self):
        ftor, fit = self._make_ftor_itq(1)
        hi = self._make_hi_linear()
        self._known_ordered_euclidean(ftor, hi, fit)

    def test_known_ordered_euclidean__itq__balltree(self):
        ftor, fit = self._make_ftor_itq(1)
        hi = self._make_hi_balltree()
        self._known_ordered_euclidean(ftor, hi, fit)
