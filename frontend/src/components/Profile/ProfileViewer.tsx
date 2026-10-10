import { useState, useEffect } from 'react';
import { User, Linkedin, MapPin, Brain, Shield, Sparkles, CheckCircle, Save } from 'lucide-react';
import { useLocationStore } from '../../store/locationStore';

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
    experience:
      'Building Sovereign Local AI Systems, Hybrid RRF Context Engines & Distributed Architecture',
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
    <div className="flex-1 flex flex-col bg-white/[0.02] border border-white/[0.08] rounded-2xl p-6 overflow-y-auto backdrop-blur-xl">
      {/* Header Banner */}
      <div className="flex items-center justify-between pb-6 border-b border-white/[0.08] flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-cyan-500 to-purple-600 flex items-center justify-center text-white shadow-[0_0_25px_rgba(0,240,255,0.3)]">
            <User size={32} />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-bold text-white tracking-wide">{profile.name}</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-400/10 text-cyan-400 border border-cyan-400/30">
                SOVEREIGN USER
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

        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-400 text-black font-semibold text-xs hover:bg-cyan-300 transition-colors shadow-[0_0_15px_rgba(0,240,255,0.2)] cursor-pointer"
        >
          {savedStatus ? <CheckCircle size={14} /> : <Save size={14} />}
          <span>{savedStatus ? 'Saved to Memory' : 'Save Changes'}</span>
        </button>
      </div>

      {/* Profile Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
        {/* LinkedIn Link Card */}
        <div className="md:col-span-2 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
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
          <span className="text-[11px] px-2 py-1 rounded bg-green-500/10 text-green-400 border border-green-500/20">
            Verified Slug
          </span>
        </div>

        {/* Professional Headline */}
        <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Professional Headline
          </label>
          <input
            type="text"
            value={profile.headline}
            onChange={(e) => setProfile({ ...profile, headline: e.target.value })}
            className="w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400"
          />
        </div>

        {/* Real-time Location */}
        <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Real-time Location
          </label>
          <input
            type="text"
            value={profile.location}
            onChange={(e) => setProfile({ ...profile, location: e.target.value })}
            className="w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400"
          />
        </div>

        {/* Skills */}
        <div className="md:col-span-2 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Skills &amp; Tech Stack
          </label>
          <input
            type="text"
            value={profile.skills}
            onChange={(e) => setProfile({ ...profile, skills: e.target.value })}
            className="w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400"
          />
        </div>

        {/* Experience */}
        <div className="md:col-span-2 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
          <label className="text-xs text-white/40 block mb-1.5 font-mono">
            Experience &amp; Focus
          </label>
          <textarea
            rows={3}
            value={profile.experience}
            onChange={(e) => setProfile({ ...profile, experience: e.target.value })}
            className="w-full bg-white/[0.05] border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-400 resize-none"
          />
        </div>
      </div>

      {/* Memory Intelligence Footer */}
      <div className="mt-6 p-4 rounded-xl bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-cyan-500/20 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain size={20} className="text-purple-400" />
          <div>
            <p className="text-xs font-semibold text-white">
              Hybrid RRF Episodic Memory Sync Active
            </p>
            <p className="text-[11px] text-white/50">
              Facts, pronouns, and preferences automatically inject into the Sandwich Context architecture.
            </p>
          </div>
        </div>
        <Sparkles size={16} className="text-cyan-400 animate-pulse" />
      </div>
    </div>
  );
};
