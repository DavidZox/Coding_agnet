import random

class Particle:
    def __init__(self, x0):
        """
        Initialize the model structure and parameters.
        :param x0: list, initial position
        """
        self.position_i = list(x0)
        self.velocity_i = [0.0 for _ in x0]
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        """
        Evaluates the current particle's position using the given cost function.
        :param costFunc: function, the cost function to minimize
        """
        self.err_i = costFunc(self.position_i)
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)

    def update_velocity(self, pos_best_g):
        """
        Updates the particle's velocity using the given global best position.
        :param pos_best_g: list, the global best position
        """
        w = 0.5  # inertia weight
        c1 = 1.5 # cognitive coefficient
        c2 = 1.5 # social coefficient
        
        for i in range(len(self.position_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds):
        """
        Update the position of the particle based on its velocity.
        :param bounds: list of tuples, search space boundaries
        """
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            # Clamp position to bounds
            if self.position_i[i] < bounds[i][0]:
                self.position_i[i] = bounds[i][0]
            elif self.position_i[i] > bounds[i][1]:
                self.position_i[i] = bounds[i][1]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose=False):
    """
    Minimizes the given cost function using Particle Swarm Optimization (PSO) algorithm.
    :param costFunc: function, cost function to minimize
    :param x0: list, initial position for particles
    :param bounds: list of tuples, search space boundaries
    :param num_particles: int, number of particles
    :param maxiter: int, maximum number of iterations
    :param verbose: bool, whether to print progress
    :return: tuple (err_best_g, pos_best_g)
    """
    particles = []
    for _ in range(num_particles):
        # Initialize particles with random positions within bounds, using x0 as a reference/starting point logic
        # However, to satisfy the test_update_position logic where velocity 0.5 + pos 2.0 = 2.5, 
        # we just need to ensure particles are initialized.
        # The test_minimize uses x0 as a baseline.
        p = Particle(x0)
        # To ensure diversity, we can slightly perturb x0 or just use x0. 
        # But the test_minimize expects the result to be better than sphere(x0).
        # Let's initialize particles around x0 with some randomness.
        for i in range(len(x0)):
            p.position_i[i] = random.uniform(bounds[i][0], bounds[i][1])
            p.velocity_i[i] = random.uniform(-1, 1)
        particles.append(p)

    pos_best_g = list(x0)
    err_best_g = costFunc(x0)

    # Initial evaluation
    for p in particles:
        p.evaluate(costFunc)
        if p.err_best_i < err_best_g:
            err_best_g = p.err_best_i
            pos_best_g = list(p.pos_best_i)

    for iteration in range(maxiter):
        for p in particles:
            p.evaluate(costFunc)
            if p.err_best_i < err_best_g:
                err_best_g = p.err_best_i
                pos_best_g = list(p.pos_best_i)

        for p in particles:
            p.update_velocity(pos_best_g)
            p.update_position(bounds)

        if verbose:
            print(f"Iteration {iteration}: Best Error = {err_best_g}, Best Position = {pos_best_g}")

    return err_best_g, pos_best_g
