import numpy as np
from pyglet.window import key

class Policy(object):
    def __init__(self):
        pass

    def action(self, obs):
        raise NotImplementedError

class InteractivePolicy(Policy):
    def __init__(self, env, agent_index):
        super(InteractivePolicy, self).__init__()
        self.env = env
        self.agent_index = agent_index
        # hard-coded keyboard events
        self.management = [False for i in range(12)]
        self.comm = [False for i in range(env.world.dim_c)]
        # register keyboard events with this environment's window
        env.viewers[agent_index].window.on_key_press = self.key_press
        env.viewers[agent_index].window.on_key_release = self.key_release
        self.pressed = False

    def action(self, obs):
        if self.env.discrete_action_input:
            m = 0
            if self.management[0]: m = 1
            if self.management[1]: m = 2
            if self.management[2]: m = 3
            if self.management[3]: m = 4
            if self.management[4]: m = 5
            if self.management[5]: m = 6
        else:
            m = np.zeros(13) # 7-d because of no-change action
            if self.management[0]: m[1] +=1.0
            if self.management[1]: m[2] +=1.0
            if self.management[2]: m[3] +=1.0
            if self.management[3]: m[4] +=1.0
            if self.management[4]: m[5] +=1.0
            if self.management[5]: m[6] +=1.0
            if self.management[6]: m[7] +=1.0
            if self.management[7]: m[8] +=1.0
            if self.management[8]: m[9] +=1.0
            if self.management[9]: m[10] +=1.0
            if self.management[10]: m[11] +=1.0
            if self.management[11]: m[12] +=1.0
            if True not in self.management:
                m[0] += 1.0
            else:
                print(f'{self.env.agents[self.agent_index]}:{m}')

        return np.concatenate([m, np.zeros(self.env.world.dim_c)])

    def key_press(self, k, mod):
        if k==key._1: self.management[0] = True
        if k==key._2: self.management[1] = True
        if k==key._3: self.management[2] = True
        if k==key._4: self.management[3] = True
        if k==key._5: self.management[4] = True
        if k==key._6: self.management[5] = True
        
        if k==key.O: self.management[0] == True
        if k==key.P: self.management[1] == True
    
    def key_release(self, k, mod):
        if k==key._1: self.management[0] = False
        if k==key._2: self.management[1] = False
        if k==key._3: self.management[2] = False
        if k==key._4: self.management[3] = False
        if k==key._5: self.management[4] = False
        if k==key._6: self.management[5] = False

        if k==key.O: self.management[0] = False
        if k==key.P: self.management[1] = False



