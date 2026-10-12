import unittest
from pso.pso_simple import minimize
from pso.cost_functions import sphere

class TestPSOSimple(unittest.TestCase):
    def test_minimize_sphere_function(self):
        initial = [1.0, 1.0]
        bounds = [(-10.0, 10.0), (-10.0, 10.0)]
        num_particles = 30
        maxiter = 100
        verbose = False

        best_error, best_position = minimize(sphere, initial, bounds, num_particles, maxiter, verbose)
        self.assertAlmostEqual(best_error, 0.0, places=5)
        self.assertAlmostEqual(best_position[0], 0.0, places=5)
        self.assertAlmostEqual(best_position[1], 0.0, places=5)

if __name__ == '__main__':
    unittest.main()
