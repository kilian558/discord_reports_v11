module.exports = {
  apps: [
    {
      name: "discord-reports",
      script: "bot.py",
      interpreter: "python3",
      cron_restart: "30 4 * * *",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
