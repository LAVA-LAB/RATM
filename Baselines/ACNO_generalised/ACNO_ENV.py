from AM_Gyms.ModelLearner import ModelLearner
from AM_Gyms.AM_Env_wrapper import AM_ENV
import numpy as np
from pomdpy.DataClasses import PositionData, BoxAction, BoxObservation, BoxState
from pomdpy.discrete_pomdp import DiscreteActionPool, DiscreteObservationPool
from pomdpy.pomdp import  StepResult
class ACNO_ENV():
    """
    Class acting as a wrapper around AM_ENV environments (i.e. openAI gyms
    with a AM-wrapper), which builds a model that can be used by POMCP by
    sampling from the environment offline.
    """

    
    def __init__(self, AM_Env:AM_ENV):
        
        # Environment & env-related variables (BAM-QMDP naming)
        self.env = ModelLearner(AM_Env)
        
        # Set up variables
        self.StateSize, self.ActionSize, self.cost, self.s_init, self.doneState = self.env.get_vars()
        self.CActionSize = self.ActionSize // 2  #both measuring & non-measuring actions
        self.EmptyObservation = -1
        self.donePenalty = 0.0
        self.selfLoopPenalty = 0.1
        
        #Set up model (Blank!)
        #self.sample_model(0)
        
        # Renaming for POMCP-algo:
        self.init_state, self.actions_n, self.states_n = self.s_init, self.ActionSize, self.StateSize
        # Other POMCP-variables
        self.solver = 'POMCP'
        self.n_start_states = 200
        self.ucb_coefficient = 5 #no optimism required
        self.seed = np.random.seed() 
        self.min_particle_count = 18
        self.max_particle_count = 22
        self.max_depth = 50
        self.action_selection_timeout = 600_000
        self.particle_selection_timeout = 2
        self.n_sims = 10_000
        self.preferred_actions = False
        self.timeout = 7_200_000
        self.discount = 0.95
        
        
        self.sampling_rewards = []
        self.sampling_steps = []

        
    #########################################
    #       POMDP-model functions:             #
    #########################################
    
    def sample_model(self, episodes = 1000):
        rewards, steps = self.env.sample(episodes)
        self.T, self.R, self.R_biased = self.env.get_model()
        return rewards, steps
        
        
    
    def reset():
        '''I don't quiet now what uses this function: TBW!''' #TODO
        pass
    
    def generate_particles(self, prev_belief, action, obs, n_particles, prev_particles, mdp=False):
        '''Sample new belief particles according to model approximation.'''
        if type(obs) is not int:
            obs = obs.position
        if type(action) is not int:
            action = action.bin_number
        
        new_particles = []
        
        # If obs not empty, than we know the next state for sure: return that!
        if obs != self.EmptyObservation:
            terminal = (obs==self.doneState)
            while new_particles.__len__() < n_particles:
                new_particles.append(BoxState(obs, terminal))
                
        else:
        # Otherwise, sample new states according to model:
            while new_particles.__len__() < n_particles:
                prev_state = np.random.choice(prev_particles).position
                next_state = np.random.choice(np.arange(self.StateSize), p=self.T[prev_state,action])
                terminal = (next_state == self.doneState)
                
                new_particles.append(BoxState(next_state, terminal))
        
        # The original has changes to self-sampling if time runs to high: I don't expect that to be necessary...
        return new_particles

    def model_step(self, state, action, rollout = False):
        """Estimates the next state and reward, using exisiting model."""
        next_state = np.random.choice(self.StateSize, p=self.T[state,action])
        if rollout:
            reward = self.R[state,action]
        else:
            reward = self.R_biased[state,action]
        done = False
        if next_state == self.doneState:
            done = True
            #reward = 0
        return next_state, reward, done
    
    def take_real_step(self, action, ignoreMeasuring = False):
        """Takes a real step in the environement, returns (reward, done). """
        # Take action
        ac, ao = action % self.CActionSize, action // self.CActionSize
        (reward, done) = self.env.real_step(ac)
        
        #Measure (if applicable)
        if not ignoreMeasuring:
            if self.is_measuring(action): # measuring:
                obs, c = self.env.measure_env()
                reward -= c
            else:
                obs = self.EmptyObservation
            return(reward, obs, done)
        return  (reward, done)

    def generate_step(self, state, action, is_mdp=False, rollout=False):
        '''As used by POMCP: models a step & return in POMCP-format'''
        # Unpack actions and states if required
        if type(action) is not int:
            action = action.bin_number
        if type(state) is not int:
            state = state.position
        
        # Simulate a step:
        rollout = False
        (next_state, reward, done) = self.model_step(state, action, rollout)
        
        # Deal with measuring/not measuring
        if self.is_measuring(action):
            obs = next_state
        else:
            obs = self.EmptyObservation
        
        return self.to_StepResult(action, obs, next_state, reward, done ), True
        # Reformat & return
        
    def to_StepResult(self, action, obs, nextState, reward,done):
        results = StepResult()
        results.action = BoxAction(action)
        results.observation = BoxObservation(obs)
        results.reward = reward
        results.is_terminal = done
        results.next_state = BoxState(nextState)
        return results
    
    
    # Model setters/getters and renamings:
    
    def update(self, step_results):
        '''Does nothing: we do not need to update according 
        to results, we only used the sampled results. '''
        pass
    
    def get_all_observations(self):
        obs = {}
        for i in range(self.StateSize):
            obs[i] = i
        obs[i+1] = self.EmptyObservation
        return obs
    
    def create_action_pool(self):
         return DiscreteActionPool(self)
     
    def get_all_actions(self, noMeasuring=False):
        '''Return all possible actions in BoxAction-format'''
        all_actions = []
        if noMeasuring:
            for i in range(self.CActionSize):
                all_actions.append(BoxAction(i))
        else:
            for i in range(self.ActionSize):
                all_actions.append(BoxAction(i))
        return all_actions

    def get_legal_actions(self, state):
        return self.get_all_actions()
    
    def get_rollout_actions(self, state):
        return self.get_all_actions(self, state, noMeasuring=True)
    
    def create_observation_pool(self, solver):
        return DiscreteObservationPool(solver)
    
    def reset_for_simulation(self):
        pass

    def sample_an_init_state(self):
        return BoxState(self.init_state)

    def create_root_historical_data(self, solver):
        return PositionData(self, self.init_state, solver)

    def belief_update(self, old_belief, action, observation):
        pass

    def get_max_undiscounted_returns(self):
        return 1.0

    def reset_for_epoch(self):
        self.env.reset_env()
        self.real_state = self.init_state
        self.t = 0

    def render(self):
        pass
                
    def make_next_position(self, state, action):
        if type(action) is not int:
            action = action.bin_number
        if type(state) is not int:
            state = state.position
        state, reward, done = self.model_step(state, action)
        return BoxState(state, done, reward), True

    def is_measuring(self,action):
        return action < self.CActionSize
