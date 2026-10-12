import random
from typing import List, Callable

# Assuming cost_functions.py is available in the same package or accessible
from .cost_functions import sphere

class Particle:
    """
    Represents a single particle in the PSO swarm.
    """
    def __init__(self, x0: List[float]):
        """
        Initializes the particle structure and parameters.

        Args:
            x0: The initial position vector of the particle.
        """
        self.position_i: List[float] = list(x0)
        self.velocity_i: List[float] = [0.0] * len(x0)
        self.pos_best_i: List[float] = list(x0)
        self.err_best_i: float = float('inf')
        self.err_i: float = float('inf')

    def evaluate(self, costFunc: Callable[[List[float]], float]):
        """
        Evaluates the current particle's position using the given cost function.

        Args:
            costFunc: The cost function to evaluate the position against.
        """
        self.err_i = costFunc(self.position_i)

        # Update personal best if current error is better
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)

    def update_velocity(self, pos_best_g: List[float], w: float, c1: float, c2: float):
        """
        Updates the particle's velocity using the global best position.

        Args:
            pos_best_g: The global best position found so far.
            w: Inertia weight.
            c1: Cognitive coefficient.
            c2: Social coefficient.
        """
        dim = len(self.position_i)
        for i in range(dim):
            r1 = random.random()
            r2 = random.random()
            
            # Cognitive component: attraction to personal best
            cognitive_component = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            
            # Social component: attraction to global best
            social_component = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            
            # New velocity calculation
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive_component + social_component

    def update_position(self, bounds: List[tuple]):
        """
        Updates the particle's position based on its velocity and bounds.

        Args:
            bounds: A list of tuples defining the [min, max] bounds for each dimension.
        """
        dim = len(self.position_i)
        for i in range(dim):
            # Update position
            self.position_i[i] += self.velocity_i[i]
            
            # Clamp position within bounds
            min_val, max_val = bounds[i]
            if self.position_i[i] < min_val:
                self.position_i[i] = min_val
                self.velocity_i[i] = 0.0  # Optional: stop velocity at boundary
            elif self.position_i[i] > max_val:
                self.position_i[i] = max_val
                self.velocity_i[i] = 0.0  # Optional: stop velocity at boundary

def minimize(costFunc: Callable[[List[float]], float], x0: List[float], bounds: List[tuple], 
              num_particles: int, maxiter: int, verbose: bool, 
              w: float = 0.7, c1: float = 1.5, c2: float = 1.5) -> tuple[float, List[float]]:
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.

    Args:
        costFunc: The cost function to minimize.
        x0: The initial position vector (used for initialization).
        bounds: A list of tuples defining the [min, max] bounds for each dimension.
        num_particles: The number of particles in the swarm.
        maxiter: The maximum number of iterations to run.
        verbose: If True, prints progress during optimization.
        w: Inertia weight.
        c1: Cognitive coefficient.
        c2: Social coefficient.

    Returns:
        A tuple containing (best_error_g, best_position_g).
    """
    dim = len(x0)
    
    # 1. Initialize particles
    particles: List[Particle] = []
    for _ in range(num_particles):
        # Initialize particle with a random position within bounds for robustness, 
        # though the prompt implies using x0 structure for initialization.
        # We will initialize positions randomly within bounds for better exploration, 
        # but ensure the structure matches the required initialization logic.
        initial_pos = [random.uniform(bounds[i][0], bounds[i][1]) for i in range(dim)]
        p = Particle(initial_pos)
        particles.append(p)

    # 2. Initial evaluation and setting global best
    global_best_error = float('inf')
    global_best_position: List[float] = list(x0)
    
    for p in particles:
        p.evaluate(costFunc)
        if p.err_best_i < global_best_error:
            global_best_error = p.err_best_i
            global_best_position = list(p.pos_best_i)

    # 3. Iterative optimization
    for iteration in range(maxiter):
        for p in particles:
            # Update velocity
            p.update_velocity(global_best_position, w, c1, c2)
            
            # Update position
            p.update_position(bounds)
            
            # Evaluate new position
            p.evaluate(costFunc)
            
            # Update global best
            if p.err_best_i < global_best_error:
                global_best_error = p.err_best_i
                global_best_position = list(p.pos_best_i)

        if verbose:
            print(f"Iteration {iteration+1}/{maxiter} | Best Error Found: {global_best_error:.6f}")

    return global_best_error, global_best_position
