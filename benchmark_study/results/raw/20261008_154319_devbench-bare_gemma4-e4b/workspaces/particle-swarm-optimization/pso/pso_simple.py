import random
import math
from typing import List, Callable, Tuple

# Assuming cost_functions.py is available in the same package or accessible
from .cost_functions import sphere

class Particle:
    """
    Represents a single particle in the PSO swarm.
    """
    def __init__(self, x0: List[float], bounds: List[Tuple[float, float]]):
        """
        Initializes the particle structure and parameters.

        :param x0: Initial position vector of the particle.
        :param bounds: List of (min, max) bounds for each dimension.
        """
        self.position_i: List[float] = list(x0)
        self.velocity_i: List[float] = [0.0] * len(x0)
        self.pos_best_i: List[float] = list(x0)
        self.err_best_i: float = float('inf')
        self.err_i: float = float('inf')
        self.bounds = bounds

    def evaluate(self, cost_func: Callable[[List[float]], float]) -> float:
        """
        Evaluates the current particle's position using the given cost function.

        :param cost_func: The cost function to evaluate.
        :return: The cost value at the current position.
        """
        self.err_i = cost_func(self.position_i)
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)
        return self.err_i

    def update_velocity(self, pos_best_g: List[float], w: float, c1: float, c2: float) -> None:
        """
        Updates the particle's velocity using the given global best position.

        :param pos_best_g: The global best position found so far.
        :param w: Inertia weight.
        :param c1: Cognitive coefficient.
        :param c2: Social coefficient.
        """
        dim = len(self.position_i)
        for i in range(dim):
            r1 = random.random()
            r2 = random.random()
            
            # PSO velocity update formula
            cognitive_component = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social_component = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive_component + social_component

    def update_position(self, bounds: List[Tuple[float, float]]) -> None:
        """
        Updates the position of the particle based on its velocity and respects bounds.

        :param bounds: The bounds [(min1, max1), (min2, max2), ...] for each dimension.
        """
        dim = len(self.position_i)
        for i in range(dim):
            # Update position
            self.position_i[i] += self.velocity_i[i]
            
            # Clamp position within bounds
            min_val, max_val = bounds[i]
            self.position_i[i] = max(min_val, min(max_val, self.position_i[i]))


def minimize(
    cost_func: Callable[[List[float]], float], 
    x0: List[float], 
    bounds: List[Tuple[float, float]], 
    num_particles: int, 
    maxiter: int, 
    verbose: bool = True,
    w: float = 0.7, 
    c1: float = 1.5, 
    c2: float = 1.5
) -> Tuple[float, List[float]]:
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.

    :param cost_func: The cost function to minimize.
    :param x0: Initial position vector (used for initialization).
    :param bounds: List of (min, max) bounds for each dimension.
    :param num_particles: The number of particles in the swarm.
    :param maxiter: The maximum number of iterations to run.
    :param verbose: If True, prints progress during optimization.
    :param w: Inertia weight.
    :param c1: Cognitive coefficient.
    :param c2: Social coefficient.
    :return: A tuple containing (best_error_g, best_position_g).
    """
    dim = len(x0)
    
    # 1. Initialization
    particles: List[Particle] = []
    
    # Initialize particles randomly within bounds for robustness, 
    # but use x0 structure for dimension consistency.
    for _ in range(num_particles):
        initial_pos = [random.uniform(bounds[i][0], bounds[i][1]) for i in range(dim)]
        particle = Particle(initial_pos, bounds)
        particles.append(particle)

    # Initialize global best
    best_error_g = float('inf')
    best_position_g: List[float] = [0.0] * dim

    # Initial evaluation of all particles
    for particle in particles:
        particle.evaluate(cost_func)
        if particle.err_best_i < best_error_g:
            best_error_g = particle.err_best_i
            best_position_g = list(particle.pos_best_i)

    # 2. Optimization Loop
    for iteration in range(maxiter):
        
        for particle in particles:
            # Update velocity
            particle.update_velocity(best_position_g, w, c1, c2)
            
            # Update position
            particle.update_position(bounds)
            
            # Evaluate new position
            particle.evaluate(cost_func)
            
            # Update global best
            if particle.err_best_i < best_error_g:
                best_error_g = particle.err_best_i
                best_position_g = list(particle.pos_best_i)

        # Verbose output
        if verbose:
            print(f"Iteration {iteration+1}/{maxiter}: Best Error Found = {best_error_g:.6f}")

    return best_error_g, best_position_g
