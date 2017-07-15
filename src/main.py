import gym
from gym import wrappers
from policy import *
from value_function import *
import scipy.signal


def init_gym(env_name='Pendulum-v0'):
    """

    :param env_name: str, OpenAI Gym environment name
    :return: 3-tuple
        env: ai gym environment
        obs_dim: observation dimensions
        act_dim: action dimensions
    """
    env = gym.make(env_name)
    obs_dim = env.observation_space.shape[0]
    act_dim = env.action_space.shape[0]

    return env, obs_dim, act_dim


def run_episode(env, policy, animate=False):
    """ Run single episode with option to animate

    Args:
        env: ai gym environment
        policy: policy with "sample" method
        animate: boolean, True uses env.render() method to animate episode

    Returns: 3-tuple of NumPy arrays
        observes: shape = (episode len, obs_dim)
        actions: shape = (episode len, act_dim)
        rewards: shape = (episode len,)
    """
    obs = env.reset()
    observes, actions, rewards = [], [], []
    done = False
    step = 0
    while not done:
        if animate:
            env.render()
        obs = obs.astype(np.float64).reshape((1, -1))/3.0
        obs = np.append(obs, [[step/2000]], axis=1)
        observes.append(obs)
        action = policy.sample(obs).reshape((1, -1)).astype(np.float64)
        actions.append(action)
        obs, reward, done, _ = env.step(action)
        if not isinstance(reward, float):
            reward = np.asscalar(reward)
        rewards.append(reward)
        step += 1

    return np.concatenate(observes), np.concatenate(actions), np.array(rewards, dtype=np.float64)


def run_policy(env, policy, min_steps, min_episodes):
    """ Run policy and collect data for a minimum of min_steps

    :param env: ai gym environment
    :param policy: policy with "sample" method
    :param min_steps: minimum number of samples to collect, completes current
    episode after min_steps reached
    :return: list dictionaries, 1 dictionary per episode. Dict key/values:
        'observes' : NumPy array of states from episode
        'actions' : NumPy array of actions from episode
        'rewards' : NumPy array of (undiscounted) rewards from episode
    """
    steps, episodes = (0, 0)
    trajectories = []
    while not (steps >= min_steps and episodes >= min_episodes):
        observes, actions, rewards = run_episode(env, policy)
        steps += observes.shape[0]
        episodes += 1
        trajectory = {'observes': observes,
                      'actions': actions,
                      'rewards': rewards}
        trajectories.append(trajectory)
    log = {'MeanReward': np.mean([t['rewards'].sum() for t in trajectories]),
           'Steps': steps}

    return log, trajectories


def view_policy(env, policy):
    """ Run policy and view using env.render() method

    :param env: ai gym environment
    :param policy: policy with "sample" method
    :return: None
    """
    return run_episode(env, policy, animate=True)


def add_disc_sum_rew(trajectories, gamma=1.0):
    """ Adds discounted sum of rewards to all timesteps of all trajectories

    :param trajectories: as returned by run_policy()
    :return: None (mutates trajectories to add 'disc_sum_rew' key)

    Args:
        gamma:
    """
    for trajectory in trajectories:
        rewards = trajectory['rewards'] * (1 - gamma)
        disc_sum_rew = scipy.signal.lfilter([1.0], [1.0, -gamma], rewards[::-1])[::-1]
        trajectory['disc_sum_rew'] = disc_sum_rew


def add_value(trajectories, val_func, gamma):
    """ Adds estimated value to all timesteps of all trajectories

    :param trajectories: as returned by run_policy()
    :return: None (mutates trajectories to add 'values' key)

    Args:
        val_func:
    """
    for trajectory in trajectories:
        observes = trajectory['observes']
        values = val_func.predict(observes)
        trajectory['values'] = values


def add_advantage(trajectories):
    """ Adds estimated advantage to all timesteps of all trajectories

    :param trajectories: as returned by run_policy()
    :return: None (mutates trajectories to add 'advantages' key)
    """
    for trajectory in trajectories:
        trajectory['advantages'] = trajectory['disc_sum_rew'] - trajectory['values']


def build_train_set(trajectories):
    """ Concatenates all trajectories into single NumPy array with first
     dimension = N = total time steps across all trajectories

    :param trajectories: trajectories after processing by add_disc_sum_rew(),
     add_value(), add_advantage()
    :return: 4-tuple of NumPy arrays
    observes: shape = (N, obs_dim)
    actions: shape = (N, act_dim)
    advantages: shape = (N,)
    disc_sum_rew: shape = (N,)
    """
    observes = np.concatenate([t['observes'] for t in trajectories])
    actions = np.concatenate([t['actions'] for t in trajectories])
    disc_sum_rew = np.concatenate([t['disc_sum_rew'] for t in trajectories])
    advantages = np.concatenate([t['advantages'] for t in trajectories])
    # normalize advantages
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    return observes, actions, advantages, disc_sum_rew


def disp_log(log):
    """Print metrics to stdout"""
    log_keys = [k for k in log.keys()]
    log_keys.sort()
    print('***** Iteration {}, Mean R = {:.0f} *****'.format(log['Iteration'],
                                                             log['MeanReward']))
    for key in log_keys:
        if key != 'Iteration' and key != 'MeanReward':
            print('{:s}: {:.3g}'.format(key, log[key]))
    print('\n')


def main(num_iter=5000,
         gamma=0.995):

    env, obs_dim, act_dim = init_gym('Hopper-v1')
    obs_dim += 1
    env = wrappers.Monitor(env, '/tmp/hopper-experiment-1', force=True)
    val_func = ValueFunction(obs_dim)
    lin_val_func = LinearValueFunction()
    policy = Policy(obs_dim, act_dim)
    for i in range(num_iter):
        log, trajectories = run_policy(env, policy, min_steps=2000, min_episodes=10)
        log['Iteration'] = i
        add_value(trajectories, val_func, gamma)
        add_disc_sum_rew(trajectories, gamma)
        add_advantage(trajectories)
        observes, actions, advantages, disc_sum_rew = build_train_set(trajectories)
        print('mean: {:.3f}, min: {:.3f}, max: {:.3f}, std: {:.3f}'.format(
            np.mean(observes), np.min(observes),
            np.max(observes), np.std(observes)))
        print('mean: {:.3f}, min: {:.3f}, max: {:.3f}, std: {:.3f}'.format(
            np.mean(actions), np.min(actions),
            np.max(actions), np.std(actions)))
        print('mean: {:.3f}, min: {:.3f}, max: {:.3f}, std: {:.3f}'.format(
            np.mean(disc_sum_rew), np.min(disc_sum_rew),
            np.max(disc_sum_rew), np.std(disc_sum_rew)))
        print('mean: {:.3f}, min: {:.3f}, max: {:.3f}, std: {:.3f}'.format(
            np.mean(advantages), np.min(advantages),
            np.max(advantages), np.std(advantages)))
        log.update(policy.update(observes, actions, advantages))
        log.update(val_func.fit(observes, disc_sum_rew))
        log.update(lin_val_func.fit(observes, disc_sum_rew))
        disp_log(log)
        # if (i + 1) % 25 == 0:
        #     view_policy(env, policy)


if __name__ == "__main__":
    main()

