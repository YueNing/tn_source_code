import drl_negotiation.utils.utils as U
import tensorflow as tf
import numpy as np
import logging
from drl_negotiation.a2c.replay_buffer import ReplayBuffer
from drl_negotiation.a2c.distributions import make_pd_type


def make_update_exp(vals, target_vals):
    polyak = 1.0 - 1e-2
    expression = []

    for var, var_target in zip(sorted(vals, key=lambda v: v.name), sorted(target_vals, key=lambda v: v.name)):
        expression.append(var_target.assign(polyak * var_target - (1 - polyak) * var))
    expression = tf.group(*expression)
    return U.function([], [], updates=[expression])


def p_predict(
        make_obs_ph,
        act_space,
        p_func,
        num_units=64,
        scope='trainer',
        reuse=None
):
    with tf.compat.v1.variable_scope(scope, reuse=reuse):
        act_pdtype = make_pd_type(act_space)

        obs_ph = make_obs_ph

        p_input = obs_ph
        p = p_func(p_input, int(act_pdtype.param_shape()[0]), scope="p_func", num_units=num_units)

        act_pd = act_pdtype.proba_distribution_from_flat(p)
        act_sample = act_pd.sample()
        act = U.function(inputs=[obs_ph], outputs=act_sample)
        return act


def p_train(make_obs_ph_n,
            act_space_n,
            p_index,
            p_func,
            q_func,
            optimizer,
            grad_norm_clipping=None,
            local_q_func=False,
            num_units=64,
            scope="trainer",
            reuse=None
            ):
    with tf.compat.v1.variable_scope(scope, reuse=reuse):
        # distributions of actions
        act_pdtype_n = [make_pd_type(act_space) for act_space in act_space_n]

        # set up placeholders
        obs_ph_n = make_obs_ph_n
        act_ph_n = [act_pdtype_n[i].sample_placeholder([None], name="action" + str(i)) for i in range(len(act_space_n))]

        # agent could just observe own space
        p_input = obs_ph_n[p_index]

        # output is probability of all actions
        p = p_func(p_input, int(act_pdtype_n[p_index].param_shape()[0]), scope="p_func", num_units=num_units)
        p_func_vars = U.scope_vars(U.absolute_scope_name("p_func"))

        # esitmate probability distribution 
        act_pd = act_pdtype_n[p_index].proba_distribution_from_flat(p)

        act_sample = act_pd.sample()
        p_reg = tf.reduce_mean(tf.square(act_pd.flatparam()))

        # for critic
        act_input_n = act_ph_n + []
        act_input_n[p_index] = act_pd.sample()

        q_input = tf.concat(obs_ph_n + act_input_n, 1)

        if local_q_func:
            q_input = tf.concat([obs_ph_n[p_index], act_input_n[p_index]], 1)

        q = q_func(q_input, 1, scope="q_func", reuse=True, num_units=num_units)[:, 0]

        # -loss s the goal of q, maximize the reward
        pg_loss = -tf.reduce_mean(q)

        loss = pg_loss + p_reg * 1e-3
        # loss = pg_loss

        optimizer_expr = U.minimize_and_clip(optimizer, loss, p_func_vars, grad_norm_clipping)

        # callback
        train = U.function(inputs=obs_ph_n + act_ph_n, outputs=loss, updates=[optimizer_expr])
        act = U.function(inputs=[obs_ph_n[p_index]], outputs=act_sample)
        p_values = U.function([obs_ph_n[p_index]], p)

        # target network
        target_p = p_func(p_input, int(act_pdtype_n[p_index].param_shape()[0]), scope="target_p_func",
                          num_units=num_units)
        target_p_func_vars = U.scope_vars(U.absolute_scope_name("target_p_func"))
        update_target_p = make_update_exp(p_func_vars, target_p_func_vars)

        target_act_sample = act_pdtype_n[p_index].proba_distribution_from_flat(target_p).sample()
        target_act = U.function(inputs=[obs_ph_n[p_index]], outputs=target_act_sample)

        return act, train, update_target_p, {"p_values": p_values, "target_act": target_act}


def q_train(make_obs_ph_n, act_space_n, q_index, q_func, optimizer, grad_norm_clipping=None, local_q_func=False,
            scope="trainer", reuse=None, num_units=64):
    with tf.compat.v1.variable_scope(scope, reuse=reuse):
        # action probability distribution
        act_pdtype_n = [make_pd_type(act_space) for act_space in act_space_n]

        obs_ph_n = make_obs_ph_n
        act_ph_n = [act_pdtype_n[i].sample_placeholder([None], name=f"action" + str(i)) for i in
                    range(len(act_space_n))]

        target_ph = tf.compat.v1.placeholder(tf.float32, [None], name="target")

        # critic could observe many information, and actions of all agents and so on.
        q_input = tf.concat(obs_ph_n + act_ph_n, 1)

        if local_q_func:
            q_input = tf.concat([obs_ph_n[q_index], act_ph_n[q_index]], 1)

        # output is not action, q-value
        q = q_func(q_input, 1, scope="q_func", num_units=num_units)[:, 0]

        q_func_vars = U.scope_vars(U.absolute_scope_name("q_func"))

        # loss of q-value, mean square error
        q_loss = tf.reduce_mean(tf.square(q - target_ph))

        # reduce the variance while keeping the bias unchanged
        q_reg = tf.reduce_mean(tf.square(q))

        loss = q_loss

        optimizer_expr = U.minimize_and_clip(optimizer, loss, q_func_vars, grad_norm_clipping)

        # callable
        train = U.function(inputs=obs_ph_n + act_ph_n + [target_ph], outputs=loss, updates=[optimizer_expr])
        q_values = U.function(obs_ph_n + act_ph_n, q)

        # target network
        target_q = q_func(q_input, 1, scope="target_q_func", num_units=num_units)[:, 0]
        target_q_func_vars = U.scope_vars(U.absolute_scope_name("target_q_func"))
        update_target_q = make_update_exp(q_func_vars, target_q_func_vars)
        target_q_values = U.function(obs_ph_n + act_ph_n, target_q)

        return train, update_target_q, {'q_values': q_values, 'target_q_values': target_q_values}


class AgentTrainer(object):
    def __init__(self, name, model, obs_shape, act_space, args):
        raise NotImplemented()

    def action(self, obs):
        raise NotImplemented()

    def experience(self, obs, act, rew, new_obs, done, terminal):
        raise NotImplemented()

    def preupdate(self):
        raise NotImplemented()

    def update(self, agent, t):
        raise NotImplemented()


class MADDPGAgentTrainer(AgentTrainer):
    def __init__(self,
                 name,
                 model,
                 obs_shape_n,
                 act_space_n,
                 agent_index,
                 args,
                 local_q_func=False,
                 ):
        """

        Args:
            name:
            model: mlpmodel
            obs_shape_n: all obs_shape
            act_space_n:
            agent_index:
            args:
            local_q_func:
        """
        self.name = name
        self.n = len(obs_shape_n)
        self.agent_index = agent_index
        self.args = args
        obs_ph_n = []

        assert len(act_space_n) == len(obs_shape_n), "Error, length of act_space_n and obs_space_n are not equal!"
        # n-observation placeholder, observation of all policy agents
        for i in range(self.n):
            obs_ph_n.append(U.BatchInput(obs_shape_n[i], name="observation" + str(i)).get())

        # q-value, critic in actor-critic 
        self.q_train, self.q_update, self.q_debug = q_train(
            scope=self.name,
            make_obs_ph_n=obs_ph_n,
            act_space_n=act_space_n,
            q_index=agent_index,
            q_func=model,
            optimizer=tf.compat.v1.train.AdamOptimizer(learning_rate=args.lr),
            grad_norm_clipping=0.5,
            local_q_func=local_q_func,
            num_units=args.num_units
        )

        # policy, actor in actor-critic
        self.act, self.p_train, self.p_update, self.p_debug = p_train(
            scope=self.name,
            make_obs_ph_n=obs_ph_n,
            act_space_n=act_space_n,
            p_index=agent_index,
            p_func=model,
            q_func=model,
            optimizer=tf.compat.v1.train.AdamOptimizer(learning_rate=args.lr),
            grad_norm_clipping=0.5,
            local_q_func=local_q_func,
            num_units=args.num_units
        )

        # replay buffer for training
        self.replay_buffer = ReplayBuffer(1e6)
        self.max_replay_buffer_len = args.batch_size * args.max_episode_len
        self.replay_sample_index = None

    def __str__(self):
        return f'MADDPGAgentTrainer:{self.name}'

    def __repr__(self):
        return f'MADDPGAgentTrainer:{self.name}'

    def action(self, obs):
        return self.act(obs[None])[0]

    def experience(self, obs, act, rew, new_obs, done, terminal):
        self.replay_buffer.add(obs, act, rew, new_obs, float(done))

    def preupdate(self):
        self.replay_sample_index = None

    def update(self, agents, t):
        if len(self.replay_buffer) < self.max_replay_buffer_len:
            return

        if not t % self.args.n_steps == 0:
            return

        logging.debug(f"update trainer {self} at step {t}!")
        self.replay_sample_index = self.replay_buffer.make_index(self.args.batch_size)
        obs_n = []
        obs_next_n = []
        act_n = []
        index = self.replay_sample_index
        for i in range(self.n):
            obs, act, rew, obs_next, done = agents[i].replay_buffer.sample_index(index)
            obs_n.append(obs)
            obs_next_n.append(obs_next)
            act_n.append(act)
        obs, act, rew, obs_next, done = self.replay_buffer.sample_index(index)

        # train q network
        num_sample = 10
        target_q = 0.0
        target_q_next = None
        for i in range(num_sample):
            target_act_next_n = [agents[i].p_debug['target_act'](obs_next_n[i]) for i in range(self.n)]
            target_q_next = self.q_debug['target_q_values'](*(obs_next_n + target_act_next_n))
            target_q += rew + self.args.gamma * (1.0 - done) * target_q_next

        target_q /= num_sample
        q_loss = self.q_train(*(obs_n + act_n + [target_q]))

        # train p network
        p_loss = self.p_train(*(obs_n + act_n))

        self.p_update()
        self.q_update()

        return [q_loss, p_loss, np.mean(target_q), np.mean(rew), np.mean(target_q_next), np.std(target_q)]
