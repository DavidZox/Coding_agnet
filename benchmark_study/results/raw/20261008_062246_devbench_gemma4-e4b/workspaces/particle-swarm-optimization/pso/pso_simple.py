import random
import math

class Particle:
    """
    Represents a single particle in the Particle Swarm Optimization (PSO) algorithm.
    """
    def __init__(self, x0: list):
        """
        Initializes the particle.

        Args:
            x0: The initial position vector (list of floats).
        """
        self.position_i = list(x0)
        
        # Initialize velocity randomly, often within a range related to bounds
        # Assuming velocity initialization is proportional to the search space size or random small values
        self.velocity_i = [random.uniform(-1.0, 1.0) for _ in x0]
        
        # Initialize personal best position and error
        self.pos_best_i = list(x0)
        self.err_i = float('inf')
        self.err_best_i = float('inf')
        
        # Note: Initial evaluation requires a cost function, which is handled externally 
        # or assumed to be handled by the caller before the first update if necessary.
        # For strict adherence to __init__(x0 list), we initialize errors to infinity.

    def evaluate(self, cost_func: callable):
        """
        Evaluates the current particle's position using the given cost function.

        Args:
            cost_func: The callable cost function.
        """
        current_error = cost_func(self.position_i)
        self.err_i = current_error
        
        if current_error < self.err_best_i:
            self.err_best_i = current_error
            self.pos_best_i = list(self.position_i)

    def update_velocity(self, pos_best_g: list):
        """
        Updates the particle's velocity using the global best position.

        Args:
            pos_best_g: The global best position found so far.
        """
        # Default PSO parameters as per the requirement to match the signature
        w = 0.7  # Inertia weight
        c1 = 1.5 # Cognitive coefficient
        c2 = 1.5 # Social coefficient
        
        new_velocity = []
        for i in range(len(self.position_i)):
            r1 = random.random()
            r2 = random.random()
            
            # PSO velocity update formula:
            # v(t+1) = w*v(t) + c1*r1*(pbest_i - x_i(t)) + c2*r2*(gbest - x_i(t))
            cognitive_component = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social_component = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            
            v_new = w * self.velocity_i[i] + cognitive_component + social_component
            new_velocity.append(v_new)
        
        self.velocity_i = new_velocity

    def update_position(self, bounds: list):
        """
        Updates the particle's position based on its velocity and bounds.

        Args:
            bounds: A list where bounds[i] is a tuple (min, max) for dimension i.
        """
        new_position = []
        for i in range(len(self.position_i)):
            # Update position: x(t+1) = x(t) + v(t+1)
            new_pos = self.position_i[i] + self.velocity_i[i]
            
            # Apply boundary constraints (clamping)
            min_bound, max_bound = bounds[i]
            new_pos = max(min_bound, min(max_bound, new_pos))
            
            new_position.append(new_pos)
            
        self.position_i = new_position

def minimize(cost_func: callable, x0: list, bounds: list, num_particles: int, maxiter: int, verbose: bool) -> tuple[float, list]:
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.

    Args:
        cost_func: The callable cost function to minimize.
        x0: The initial position vector (list of floats) for the first particle.
        bounds: A list where bounds[i] is a tuple (min, max) for dimension i.
        num_particles: The number of particles in the swarm.
        maxiter: The maximum number of iterations to run.
        verbose: If True, prints the progress of the optimization each iteration.

    Returns:
        A tuple containing (err_best_g, pos_best_g), where err_best_g is the 
        global best error found and pos_best_g is the corresponding best position.
    """
    # 1. Initialize num_particles instances of Particle
    particles = [Particle(list(x0)) for _ in range(num_particles)]
    
    # Initialize global best
    err_best_g = float('inf')
    pos_best_g = list(x0)

    # Initial evaluation for all particles to set initial pbest and gbest
    for particle in particles:
        particle.evaluate(cost_func)
        if particle.err_best_i < err_best_g:
            err_best_g = particle.err_best_i
            pos_best_g = list(particle.pos_best_i)

    # 2. Iterate maxiter times
    for iteration in range(maxiter):
        
        # 2a. Evaluate and update pbest for each particle (already done partially above, but re-evaluate for safety/completeness)
        for particle in particles:
            particle.evaluate(cost_func)
            
            # 2b. Track global best
            if particle.err_best_i < err_best_g:
                err_best_g = particle.err_best_i
                pos_best_g = list(particle.pos_best_i)
        
        # 2c. Update velocity and position for each particle
        for particle in particles:
            # Update velocity using current global best
            particle.update_velocity(pos_best_g)
            # Update position using bounds
            particle.update_position(bounds)
            
            # Re-evaluate after movement to update pbest for the next iteration
            particle.evaluate(cost_func)
            
            # Update global best again after movement and evaluation
            if particle.err_best_i < err_best_g:
                err_best_g = particle.err_best_i
                pos_best_g = list(particle.pos_best_i)

        # 2d. Verbose output
        if verbose:
            print(f"Iteration {iteration+1}/{maxiter}: Best Error = {err_best_g:.6f}, Best Position = {pos_best_g}")

    # 3. Return final results
    return err_best_g, pos_best_g
