import math
import random

class Particle:
    def __init__(self, x0):
        """
        Initialize the particle.
        :param x0: Initial position as a list.
        """
        self.position_i = list(x0)
        self.velocity_i = [0.0] * len(x0)
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        """
        Evaluates the current particle's position using the given cost function.
        """
        self.err_i = costFunc(self.position_i)
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)

    def update_velocity(self, pos_best_g):
        """
        Updates the particle's velocity using the given global best position.
        Standard PSO velocity update: v = w*v + c1*r1*(pbest - x) + c2*r2*(gbest - x)
        """
        w = 0.5  # Inertia weight
        c1 = 1.5 # Cognitive coefficient
        c2 = 1.5 # Social coefficient
        
        for i in range(len(self.position_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds):
        """
        Updates the particle's position based on its velocity and ensures it stays within bounds.
        """
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            
            # Clamp to bounds
            lower, upper = bounds[i]
            if self.position_i[i] < lower:
                self.position_i[i] = lower
            elif self.position_i[i] > upper:
                self.position_i[i] = upper

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose=False):
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.
    """
    dim = len(x0)
    particles = []
    
    # Initialize particles
    for _ in range(num_particles):
        # Random initial position within bounds
        start_pos = []
        for i in range(dim):
            low, high = bounds[i]
            start_pos.append(random.uniform(low, high))
        
        p = Particle(start_pos)
        p.evaluate(costFunc)
        particles.append(p)

    # Initialize global best
    pos_best_g = list(particles[0].pos_best_i)
    err_best_g = particles[0].err_best_i
    
    for p in particles:
        if p.err_best_i < err_best_g:
            err_best_g = p.err_best_i
            pos_best_g = list(p.pos_best_i)

    # Optimization loop
    for iteration in range(maxiter):
        for p in particles:
            p.update_velocity(pos_best_g)
            p.update_position(bounds)
            p.evaluate(costFunc)
            
            if p.err_best_i < err_best_g:
                err_best_g = p.err_best_i
                pos_best_g = list(p.pos_best_i)
        
        if verbose:
            print(f"Iteration {iteration + 1}: Best Error = {err_best_g}")

    return err_best_g, pos_best_g
