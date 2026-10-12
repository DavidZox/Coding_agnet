import random

class Particle:
    def __init__(self, x0: list):
        self.position_i = list(x0)
        self.velocity_i = [0.0 for _ in x0]
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        self.err_i = costFunc(self.position_i)
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)

    def update_velocity(self, pos_best_g: list):
        # Standard PSO velocity update coefficients
        w = 0.5  # inertia weight
        c1 = 1.5 # cognitive coefficient
        c2 = 1.5 # social coefficient
        
        for i in range(len(self.velocity_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds: list):
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            # Clamp position within bounds [min, max]
            # bounds is expected to be a list of tuples/lists [(min, max), ...]
            lower, upper = bounds[i]
            if self.position_i[i] < lower:
                self.position_i[i] = lower
            elif self.position_i[i] > upper:
                self.position_i[i] = upper

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose=False):
    # Initialize particles
    particles = []
    for _ in range(num_particles):
        # Randomize initial position within bounds for each particle
        initial_pos = [random.uniform(b[0], b[1]) for b in bounds]
        p = Particle(initial_pos)
        particles.append(p)

    err_best_g = float('inf')
    pos_best_g = list(x0)

    for iteration in range(maxiter):
        for p in particles:
            p.evaluate(costFunc)
            if p.err_best_i < err_best_g:
                err_best_g = p.err_best_i
                pos_best_g = list(p.pos_best_i)

        if verbose:
            print(f"Iteration {iteration + 1}/{maxiter}: Best Error = {err_best_g}")

        for p in particles:
            p.update_velocity(pos_best_g)
            p.update_position(bounds)

    if verbose:
        print(f"Optimization finished.")
        print(f"Best Solution: {pos_best_g}")
        print(f"Best Value: {err_best_g}")

    return err_best_g, pos_best_g
