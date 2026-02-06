import {
  Client,
  GatewayIntentBits,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  InteractionType
} from "discord.js";

import {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  AudioPlayerStatus
} from "@discordjs/voice";

import { YtDlp } from "yt-dlp-wrap";
import fs from "fs";
import path from "path";

const BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE";
const VOICE_CHANNEL_ID = "1454791933280129219";
const TEXT_CHANNEL_ID  = "1454791933280129219";

const MUSIC_DIR = "./music";
if (!fs.existsSync(MUSIC_DIR)) fs.mkdirSync(MUSIC_DIR);

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMessages
  ]
});

const queues = new Map();
const panelMessage = new Map();
const mutedUsers = new Set();

const player = createAudioPlayer();
const ytdlp = new YtDlp();

function fmt(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function progressBar(cur, total) {
  const len = 18;
  const filled = Math.floor((cur / total) * len);
  return "▬".repeat(filled) + "🔘" + "▬".repeat(len - filled);
}

function buildEmbed(guild, status) {
  const queue = queues.get(guild.id) || [];

  const embed = new EmbedBuilder()
    .setTitle("🎶 Music Control Panel")
    .setDescription(status)
    .setColor(0x1DB954)
    .setFooter({ text: "E Sports Music • Premium Mode" });

  if (player.state.status === AudioPlayerStatus.Playing) {
    const s = player.state.resource.metadata;
    const elapsed = (Date.now() - s.start) / 1000;

    embed.addFields({
      name: "🎧 Now Playing",
      value:
        `**${s.title}**\n` +
        `👤 ${s.requester}\n` +
        `${fmt(elapsed)} ${progressBar(elapsed, s.duration)} ${fmt(s.duration)}`
    });
  } else {
    embed.addFields({ name: "🎧 Now Playing", value: "Nothing" });
  }

  if (queue.length) {
    embed.addFields({
      name: "⏭️ Next Up",
      value: `**${queue[0].title}**\n👤 ${queue[0].requester}`
    });
  } else {
    embed.addFields({ name: "⏭️ Next Up", value: "Nothing" });
  }

  return embed;
}

function buildButtons() {
  return [
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId("add").setLabel("Add Song").setEmoji("⬇️").setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId("pause").setEmoji("⏸").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("resume").setEmoji("▶️").setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId("skip").setEmoji("⏭").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("mute").setLabel("Mute / Unmute").setEmoji("🔇").setStyle(ButtonStyle.Secondary)
    )
  ];
}

async function sendOrUpdatePanel(guild, channel, embed) {
  const old = panelMessage.get(guild.id);
  const msgs = await channel.messages.fetch({ limit: 1 });
  const latest = msgs.first();

  if (old && latest && latest.id === old.id) {
    await old.edit({ embeds: [embed], components: buildButtons() });
    return;
  }

  if (old) await old.delete().catch(() => {});
  const msg = await channel.send({ embeds: [embed], components: buildButtons() });
  panelMessage.set(guild.id, msg);
}

client.on("ready", async () => {
  console.log(`Logged in as ${client.user.tag}`);

  const guild = client.guilds.cache.first();
  const vc = guild.channels.cache.get(VOICE_CHANNEL_ID);
  const tc = guild.channels.cache.get(TEXT_CHANNEL_ID);

  const conn = joinVoiceChannel({
    channelId: vc.id,
    guildId: guild.id,
    adapterCreator: guild.voiceAdapterCreator
  });

  conn.subscribe(player);
  await sendOrUpdatePanel(guild, tc, buildEmbed(guild, "🎧 Ready"));
});

client.login(BOT_TOKEN);
