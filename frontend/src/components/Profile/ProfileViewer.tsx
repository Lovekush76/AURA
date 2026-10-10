import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Linkedin, MapPin, Brain, Shield, Sparkles, CheckCircle, Save } from 'lucide-react';
import { useLocationStore } from '../../store/locationStore';
import { Tilt3DCard, MiniNeuralOrb3D } from '../HUD/Dynamic3DElements';

interface ProfileData {
  name?: string;
  linkedin_url?: string;
  headline?: string;
  skills?: string;
  experience?: string;
  education?: string;
  location?: string;
}

export const ProfileViewer = () => {
  const { location } = useLocationStore();
  const [profile, setProfile] = useState<ProfileData>({
    name: 'Lovekush Kumar',
    linkedin_url: 'https://www.linkedin.com/in/lovekush-kumar-9478b4183/',
    headline: 'Senior Software Engineer / AI Architect',
    skills: 'Python, TypeScript, React, Docker, PyTorch, FastAPI, Ollama, NVIDIA NIM',
    experience: 'Building Sovereign Local AI Systems, Hybrid RRF Context Engines & Distributed Architecture',
    education: 'Computer Science & Engineering',
    location: `${location.city}, ${location.country}`
  });
  const [savedStatus, setSavedStatus] = useState(false);

  useEffect(() => {
    if (location.city) {
      setProfile((prev) => ({
        ...prev,
        location: `${location.city}, ${location.country}`
      }));
    }
  }, [location]);

  const handleSave = () => {
    setSavedStatus(true);
    setTimeout(() => setSavedStatus(false), 2500);
  };

  return (
    <div className="aura-panel-3d flex-1 flex flex-col rounded-2xl p-6 overflow-y-auto preserve-3d relative">
      {/* Header Banner with 3D Levitating Identity Core */}
      <div className="flex items-center justify-between pb-6 border-b border-white/[0.08] flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <motion.div
            animate={{ y: [0, -5, 0], rotateY: [-8, 8, -8] }}
            transition={{ duration: 4.2, repeat: Infinity, ease: 'easeInOut' }}
            className="rounded-2xl bg-gradient-to-tr from-cyan-500/20 to-purple-600/20 border border-cyan-400/40 p-1 shadow-[0_0_28px_rgba(0,240,255,0.3)]"
          >
            <MiniNeuralOrb3D size={60} active={savedStatus} colorMode="cyan" />
          </motion.div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-bold text-white tracking-wide aura-text-glow-cyan">
                {profile.name}
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-400/15 text-cyan-300 border border-cyan-400/35 font-mono">
                SOVEREIGN ARCHITECT
              </span>
            </div>
            <p className="text-xs text-white/50 mt-0.5 flex items-center gap-1.5 flex-wrap">
              <MapPin size={12} className="text-cyan-400" />
              <span>{profile.location || 'Local Workspace'}</span>
              <span>•</span>
              <Shield size={12} className="text-green-400" />
              <span className="text-green-400">10M Episodic Vault + RRF Hybrid</span>
            </p>
          </div>
        </div>

        <motion.button
          whileHover={{ scale: 1.06, y: -2, rotateX: 8 }}
          whileTap={{ scale: 0.94 }}
          onClick={handleSave}
          className="aura-btn-3d flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-400 text-black font-semibold text-xs hover:bg-cyan-300 transition-colors shadow-[0_0_18px_rgba(0,240,255,0.3)] cursor-pointer"
        >
          {savedStatus ? <CheckCircle size={14} /> : <Save size={14} />}
          <span>{savedStatus ? 'Saved to 3D Memory' : 'Save Changes'}</span>
        </motion.button>
      </div>

      {/* 3D Tilted Profile Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6 preserve-3d">
        {/* LinkedIn Link Card */}
        <Tilt3DCard
          intensity={5}
          className="md:col-span-2 aura-card-3d p-4 rounded-xl flex items-center justify-between flex-wrap gap-3"
        >
          <div className="flex items-center gap-3 relative z-30">
            <div className="w-10 h-10 rounded-xl bg-[#0077B5]/20 border border-[#0077B5]/40 flex items-center justify-center text-[#0077B5]">
              <Linkedin size={20} />
            </div>
            <div>
              <p className="text-xs text-white/40 font-mono">Linked Identity</p>
              <a
                href={profile.linkedin_url}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-semibold text-cyan-300 hover:underline truncate block max-w-lg"
              >
                {profile.linkedin_url}
              </a>
            </div>
          </div>
          <span className="text-[11px] px-2 py-1 rounded bg-green-500/10 text-green-400 border border-green-500/20 font-mono">
            Verified Slug
          </span>
        </Tilt3DCard>

        {/* Professional Headline */}
        <Tilt3DCard intensity={6} className="aura-card-3d p-4 rounded-xl">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Professional Headline
          </label>
          <input
            type="text"
            value={profile.headline}
            onChange={(e) => setProfile({ ...profile, headline: e.target.value })}
            className="relative z-30 w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400"
          />
        </Tilt3DCard>

        {/* Real-time Location */}
        <Tilt3DCard intensity={6} className="aura-card-3d p-4 rounded-xl">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Real-time Location
          </label>
          <input
            type="text"
            value={profile.location}
            onChange={(e) => setProfile({ ...profile, location: e.target.value })}
            className="relative z-30 w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400"
          />
        </Tilt3DCard>

        {/* Skills */}
        <Tilt3DCard intensity={5} className="md:col-span-2 aura-card-3d p-4 rounded-xl">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Skills &amp; Tech Stack
          </label>
          <input
            type="text"
            value={profile.skills}
            onChange={(e) => setProfile({ ...profile, skills: e.target.value })}
            className="relative z-30 w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400"
          />
        </Tilt3DCard>

        {/* Experience */}
        <Tilt3DCard intensity={5} className="md:col-span-2 aura-card-3d p-4 rounded-xl">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Experience &amp; Focus
          </label>
          <textarea
            rows={3}
            value={profile.experience}
            onChange={(e) => setProfile({ ...profile, experience: e.target.value })}
            className="relative z-30 w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400 resize-none"
          />
        </Tilt3DCard>
      </div>

      {/* Memory Intelligence Footer */}
      <Tilt3DCard
        intensity={4}
        className="mt-6 p-4 rounded-xl bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-cyan-500/25 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <Brain size={20} className="text-purple-400 animate-pulse" />
          <div>
            <p className="text-xs font-semibold text-white">
              Hybrid RRF Episodic Memory Sync Active
            </p>
            <p className="text-[11px] text-white/50">
              Facts, pronouns, and preferences automatically inject into the Sandwich Context architecture.
            </p>
          </div>
        </div>
        <Sparkles size={16} className="text-cyan-400 animate-spin" style={{ animationDuration: '6s' }} />
      </Tilt3DCard>
    </div>
  );
};
