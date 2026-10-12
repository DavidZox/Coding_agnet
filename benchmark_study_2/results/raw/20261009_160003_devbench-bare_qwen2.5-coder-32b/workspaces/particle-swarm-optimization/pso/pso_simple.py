import random

class Particle:
    def __init__(self, x0):
        self.position_i = []          # particle position
        self.velocity_i = []          # particle velocity
        self.pos_best_i = []          # best position individual
        self.err_best_i = -1          # best error individual
        self.err_i = -1               # error individual

        for i in range(0, num_dimensions):
            self.velocity_i.append(random.uniform(-1, 1))
            self.position_i.append(x0[i])

    def evaluate(self, costFunc):
        self.err_i = costFunc(self.position_i)

        if self.err_i < self.err_best_i or self.err_best_i == -1:
            self.pos_best_i = self.position_i
            self.err_best_i = self.err_i

    def update_velocity(self, pos_best_g):
        w = 0.5       # constant inertia weight (how much to weigh the previous velocity)
        c1 = 1        # cognative constant
        c2 = 2        # social constant

        for i in range(0, num_dimensions):
            r1 = random.random()
            r2 = random.random()

            vel_cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            vel_social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + vel_cognitive + vel_social

    def update_position(self, bounds):
        for i in range(0, num_dimensions):
            self.position_i[i] = self.position_i[i] + self.velocity_i[i]

            if self.position_i[i] > bounds[i][1]:
                self.position_i[i] = bounds[i][1]

            if self.position_i[i] < bounds[i][0]:
                self.position_i[i] = bounds[i][0]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose):
    global num_dimensions
    num_dimensions = len(x0)
    err_best_g = -1                   # best error for group
    pos_best_g = []                   # best position for group

    swarm = []
    for i in range(0, num_particles):
        swarm.append(Particle(x0))

    for i in range(0, maxiter):
        for j in range(0, num_particles):
            swarm[j].evaluate(costFunc)

            if swarm[j].err_i < err_best_g or err_best_g == -1:
                pos_best_g = list(swarm[j].position_i)
                err_best_g = float(swarm[j].err_i)

        for j in range(0, num_particles):
            swarm[j].update_velocity(pos_best_g)
            swarm[j].update_position(bounds)

        if verbose:
            print(f"Iteration {i}: Best Solution = {err_best_g}")

    return (err_best_g, pos_best_g)
