import env



def main():
    env = TanksEnv()
    # model = PPO("MlpPolicy", env, verbose=1)
    # model.learn(total_timesteps=...)
    # model.save("tanks_ppo")

if __name__ == "__main__":
    main()
