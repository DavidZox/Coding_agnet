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
        # Standard PSO parameters: w=0.5, c1=1.5, c2=1.5
        w = 0.5
        c1 = 1.5
        c2 = 1.5
        for i in range(len(self.velocity_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds: list):
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            # Clamp position to bounds
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
        initial_pos = []
        for i in range(len(x0)):
            low, high = bounds[i]
            initial_pos.append(random.uniform(low, high))
        particles.append(Particle(initial_pos))

    # Initialize global best
    err_best_g = float('inf')
    pos_best_g = list(x0)

    for iteration in range(maxiter):
        for particle in particles:
            particle.evaluate(costFunc)
            if particle.err_i < err_best_g:
                err_best_g = particle.err_i
                pos_best_g = list(particle.position_i)

        if verbose:
            print(f"Iteration {iteration + 1}/{maxiter}: Best Error = {err_best_g}")

        for particle in particles:
            particle.update_velocity(pos_best_g)
            particle.update_position(bounds)

    if verbose:
        print(f"Optimization finished.")
        print(f"Best Solution: {pos_best_g}")
        print(f"Best Value: {err_best_g}")

    return err_best_g, pos_best_g
