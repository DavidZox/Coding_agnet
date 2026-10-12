import random

class Particle:
    def __init__(self, x0):
        self.position_i = x0
        self.velocity_i = [0.0 for _ in range(len(x0))]
        self.pos_best_i = []
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        self.err_i = costFunc(self.position_i)

        if self.err_i < self.err_best_i:
            self.pos_best_i = self.position_i.copy()
            self.err_best_i = self.err_i

    def update_velocity(self, pos_best_g):
        w = 0.5  # inertia weight
        c1 = 1.5  # cognitive (particle) weight
        c2 = 1.5  # social (swarm) weight

        for i in range(len(self.velocity_i)):
            r1 = random.random()
            r2 = random.random()

            vel_cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            vel_social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + vel_cognitive + vel_social

    def update_position(self, bounds):
        for i in range(len(self.position_i)):
            self.position_i[i] = self.position_i[i] + self.velocity_i[i]

            if self.position_i[i] > bounds[i][1]:
                self.position_i[i] = bounds[i][1]

            if self.position_i[i] < bounds[i][0]:
                self.position_i[i] = bounds[i][0]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose):
    err_best_g = float('inf')
    pos_best_g = []

    swarm = [Particle(x0) for _ in range(num_particles)]

    for i in range(maxiter):
        for particle in swarm:
            particle.evaluate(costFunc)

            if particle.err_i < err_best_g:
                pos_best_g = list(particle.position_i)
                err_best_g = float(particle.err_i)

        for particle in swarm:
            particle.update_velocity(pos_best_g)
            particle.update_position(bounds)

        if verbose:
            print(f"Iteration {i}: Best error = {err_best_g}, Best position = {pos_best_g}")

    return (err_best_g, pos_best_g)
