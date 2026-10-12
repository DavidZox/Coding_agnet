import random

class Particle:
    def __init__(self, x0):
        """
        Initialize the particle.
        :param x0: initial position list
        """
        self.position_i = list(x0)
        self.velocity_i = [0.0 for _ in range(len(x0))]
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        """
        Evaluates the current particle's position using the given cost function.
        :param costFunc: function to minimize
        """
        self.err_i = costFunc(self.position_i)
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)
        return self.err_i

    def update_velocity(self, pos_best_g):
        """
        Updates the particle's velocity using the given global best position.
        Standard PSO parameters: w=0.5, c1=1.5, c2=1.5
        :param pos_best_g: global best position list
        """
        w = 0.5
        c1 = 1.5
        c2 = 1.5
        for i in range(len(self.velocity_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds):
        """
        Update the position of the particle based on its velocity.
        :param bounds: list of (min, max) tuples for each dimension
        """
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            # Keep position within bounds
            if self.position_i[i] < bounds[i][0]:
                self.position_i[i] = bounds[i][0]
            elif self.position_i[i] > bounds[i][1]:
                self.position_i[i] = bounds[i][1]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose=False):
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.
    :param costFunc: function to minimize
    :param x0: initial position (used to derive dimension)
    :param bounds: list of (min, max) tuples
    :param num_particles: number of particles
    :param maxiter: maximum number of iterations
    :param verbose: if True, print progress
    :return: (err_best_g, pos_best_g)
    """
    dim = len(x0)
    particles = []
    
    # Initialize particles
    for _ in range(num_particles):
        # Random initial position within bounds
        start_pos = [random.uniform(bounds[i][0], bounds[i][1]) for i in range(dim)]
        p = Particle(start_pos)
        particles.append(p)

    err_best_g = float('inf')
    pos_best_g = list(x0)

    for iteration in range(maxiter):
        for p in particles:
            # 1. Evaluate
            p.evaluate(costFunc)
            
            # 2. Update Global Best
            if p.err_i < err_best_g:
                err_best_g = p.err_i
                pos_best_g = list(p.position_i)

        if verbose:
            print(f"Iteration {iteration + 1}/{maxiter}: Best Error = {err_best_g}")

        # 3. Update Velocity and Position
        for p in particles:
            p.update_velocity(pos_best_g)
            p.update_position(bounds)

    return err_best_g, pos_best_g
