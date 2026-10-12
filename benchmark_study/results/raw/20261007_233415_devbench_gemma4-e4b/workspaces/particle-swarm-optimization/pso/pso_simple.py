import random
import math

class Particle:
    """
    Represents a single particle in the Particle Swarm Optimization (PSO) algorithm.
    """
    def __init__(self, x0: list):
        """
        Initializes the particle structure and parameters.

        Args:
            x0: The initial position vector of the particle (list of floats).
        """
        self.position_i = list(x0)
        # Initialize velocity to zero
        self.velocity_i = [0.0] * len(x0)
        # Initialize personal best position to initial position
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        """
        Evaluates the current particle's position using the given cost function.

        Args:
            costFunc: The function to evaluate the cost (e.g., sphere function).
        """
        current_error = costFunc(self.position_i)
        self.err_i = current_error

        # Update personal best if current error is better
        if current_error < self.err_best_i:
            self.err_best_i = current_error
            self.pos_best_i = list(self.position_i)

    def update_velocity(self, pos_best_g: list):
        """
        Updates the particle's velocity using the given global best position.

        Note: This implementation assumes standard PSO coefficients (w, c1, c2) 
        are handled by the calling function (minimize). For simplicity based on the UML, 
        we use placeholder logic or assume coefficients are implicitly handled/fixed 
        if they are not passed, but to match standard PSO, we must assume they are available 
        or modify the signature if necessary. Based on the UML, only pos_best_g is listed.
        We will fix them here for execution.
        """
        w = 0.7  # Inertia weight
        c1 = 1.5 # Cognitive coefficient
        c2 = 1.5 # Social coefficient
        
        dim = len(self.position_i)
        for i in range(dim):
            r1 = random.random()
            r2 = random.random()

            # Cognitive component: attraction to personal best
            cognitive_component = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            # Social component: attraction to global best
            social_component = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            # Inertia component
            inertia_component = w * self.velocity_i[i]

            # Update velocity
            self.velocity_i[i] = inertia_component + cognitive_component + social_component

    def update_position(self, bounds: list):
        """
        Updates the particle's position based on its velocity and bounds.

        Args:
            bounds: A list where bounds[i] is a tuple (min, max) for dimension i.
        """
        dim = len(self.position_i)
        for i in range(dim):
            # Update position
            new_position = self.position_i[i] + self.velocity_i[i]

            # Apply bounds clamping
            min_bound = bounds[i][0]
            max_bound = bounds[i][1]

            if new_position < min_bound:
                self.position_i[i] = min_bound
                # Simple handling: stop velocity at boundary
                self.velocity_i[i] = 0
            elif new_position > max_bound:
                self.position_i[i] = max_bound
                # Simple handling: stop velocity at boundary
                self.velocity_i[i] = 0
            else:
                self.position_i[i] = new_position

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose):
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.

    Args:
        costFunc: The function to evaluate the cost.
        x0: The initial position vector (used for initialization).
        bounds: A list where bounds[i] is a tuple (min, max) for dimension i.
        num_particles: The number of particles in the swarm.
        maxiter: The maximum number of iterations.
        verbose: If True, prints progress during optimization.

    Returns:
        tuple: (best_error_g, best_position_g)
    """
    # 1. Initialization
    particles = []
    
    # Initialize global best
    best_error_g = float('inf')
    best_position_g = None

    for _ in range(num_particles):
        # Initialize particle with a random position within bounds
        initial_position = [
            random.uniform(bounds[i][0], bounds[i][1]) for i in range(len(x0))
        ]
        particle = Particle(initial_position)
        particles.append(particle)

        # Evaluate initial position and update personal/global best
        particle.evaluate(costFunc)
        
        if particle.err_best_i < best_error_g:
            best_error_g = particle.err_best_i
            best_position_g = list(particle.pos_best_i)

    # 2. Iteration Loop
    for iteration in range(maxiter):
        for particle in particles:
            # Update velocity and position
            particle.update_velocity(best_position_g)
            particle.update_position(bounds)
            
            # Evaluate new position
            particle.evaluate(costFunc)
            
            # Update personal best
            # (This is handled inside particle.evaluate, but we check against global best here)
            
            # Update global best
            if particle.err_best_i < best_error_g:
                best_error_g = particle.err_best_i
                best_position_g = list(particle.pos_best_i)

        # 3. Verbose Output
        if verbose:
            print(f"Iteration {iteration+1}/{maxiter} | Best Error Found: {best_error_g:.6f} | Best Position: {[f'{p:.4f}' for p in best_position_g]}")

    return best_error_g, best_position_g
