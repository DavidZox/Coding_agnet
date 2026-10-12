import math
import random

class Particle:
    """
    Represents a single particle in the PSO algorithm.
    """
    def __init__(self, x0: list):
        """
        Initializes the particle.

        Args:
            x0: The initial position vector of the particle.
        """
        self.position_i = list(x0)
        # Initialize velocity randomly or to zero (assuming zero for simplicity based on typical PSO setup if not specified)
        # Since no specific velocity initialization is given, we initialize it to zeros matching the dimension of x0.
        self.velocity_i = [0.0] * len(x0)
        
        # Initialize personal best position and error
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        
        # Current particle error
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        """
        Evaluates the current particle's position using the given cost function.

        Args:
            costFunc: The function used to calculate the cost (fitness) of the position.
        """
        self.err_i = costFunc(self.position_i)
        self.update_pbest()

    def update_velocity(self, pos_best_g: list):
        """
        Updates the particle's velocity using the global best position.

        Args:
            pos_best_g: The current global best position found by the swarm.
        """
        # PSO parameters as specified in the task: c1=2.0, c2=2.0, w=0.729
        w = 0.729  # Inertia weight
        c1 = 2.0   # Cognitive coefficient
        c2 = 2.0   # Social coefficient
        
        new_velocity = []
        for i in range(len(self.position_i)):
            r1 = random.random()
            r2 = random.random()
            
            # PSO velocity update formula:
            # v(t+1) = w*v(t) + c1*r1*(pbest_i - x_i) + c2*r2*(gbest - x_i)
            cognitive_component = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social_component = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            
            new_v = w * self.velocity_i[i] + cognitive_component + social_component
            new_velocity.append(new_v)
        
        self.velocity_i = new_velocity

    def update_position(self, bounds: list):
        """
        Updates the particle's position based on its velocity and bounds.

        Args:
            bounds: A list of tuples or lists defining the [min, max] bounds for each dimension.
        """
        new_position = []
        for i in range(len(self.position_i)):
            # Update position: x(t+1) = x(t) + v(t+1)
            new_x = self.position_i[i] + self.velocity_i[i]
            
            # Apply bounds clamping
            min_bound = bounds[i][0]
            max_bound = bounds[i][1]
            
            new_x = max(min_bound, min(max_bound, new_x))
            new_position.append(new_x)
            
        self.position_i = new_position

    def update_pbest(self):
        """
        Updates the particle's personal best position if the current position is better.
        """
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)

def minimize(costFunc: callable, x0: list, bounds: list, num_particles: int, maxiter: int, verbose: bool) -> tuple[float, list]:
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.

    Args:
        costFunc: The function used to calculate the cost (fitness) of the position.
        x0: The initial position vector (used for initialization).
        bounds: A list of tuples or lists defining the [min, max] bounds for each dimension.
        num_particles: The number of particles in the swarm.
        maxiter: The maximum number of iterations to run.
        verbose: If True, prints the best solution found in each iteration.

    Returns:
        A tuple containing (err_best_g, pos_best_g), where err_best_g is the global best error
        and pos_best_g is the global best position found.
    """
    # 1. Initialization
    particles = []
    
    # Initialize global best
    err_best_g = float('inf')
    pos_best_g = list(x0) # Initialize with a starting point, will be updated in the first evaluation

    for _ in range(num_particles):
        # Create particle, initializing its position based on x0 (or randomly within bounds if x0 is just a reference)
        # For simplicity matching the structure, we initialize particles using x0 as the base for their starting position.
        # In a real scenario, particles would be initialized randomly within bounds.
        particle = Particle(x0) 
        particles.append(particle)

    # Initial evaluation to set initial global best
    for particle in particles:
        particle.evaluate(costFunc)
        if particle.err_best_i < err_best_g:
            err_best_g = particle.err_best_i
            pos_best_g = list(particle.pos_best_i)

    # 2. Iteration Loop
    for t in range(maxiter):
        
        # 2a. Evaluate and update personal bests (already done partially above, but needs to be done per iteration)
        for particle in particles:
            particle.evaluate(costFunc)
            
            # 2b. Update global best
            if particle.err_best_i < err_best_g:
                err_best_g = particle.err_best_i
                pos_best_g = list(particle.pos_best_i)
        
        # 2c. Update velocity and position for all particles
        for particle in particles:
            particle.update_velocity(pos_best_g)
            particle.update_position(bounds)
        
        # 2d. Verbose output
        if verbose:
            print(f"Iteration {t+1}/{maxiter}: Best Error = {err_best_g:.6f}, Best Position = {pos_best_g}")

    # 3. Return final results
    return err_best_g, pos_best_g
