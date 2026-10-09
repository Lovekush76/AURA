import { create } from 'zustand';

export interface LocationData {
  latitude: number | null;
  longitude: number | null;
  city: string;
  region: string;
  country: string;
  timezone: string;
  status: 'detecting' | 'ready' | 'denied' | 'fallback';
}

interface LocationStore {
  location: LocationData;
  detectLocation: () => Promise<void>;
  setLocation: (loc: Partial<LocationData>) => void;
}

export const useLocationStore = create<LocationStore>((set) => ({
  location: {
    latitude: null,
    longitude: null,
    city: 'Detecting...',
    region: '',
    country: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata',
    status: 'detecting'
  },
  setLocation: (loc) =>
    set((state) => ({
      location: { ...state.location, ...loc }
    })),
  detectLocation: async () => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';
    
    // First default fallback based on detected timezone
    let defaultCity = tz.includes('/') ? tz.split('/')[1].replace('_', ' ') : 'Local';
    let defaultCountry = tz.includes('Kolkata') || tz.includes('India') ? 'India' : 'Local';

    set({
      location: {
        latitude: null,
        longitude: null,
        city: defaultCity,
        region: '',
        country: defaultCountry,
        timezone: tz,
        status: 'ready'
      }
    });

    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          try {
            // Optional reverse geocoding via public free client endpoint
            const res = await fetch(
              `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lon}&localityLanguage=en`
            );
            if (res.ok) {
              const data = await res.json();
              set({
                location: {
                  latitude: lat,
                  longitude: lon,
                  city: data.city || data.locality || defaultCity,
                  region: data.principalSubdivision || '',
                  country: data.countryName || defaultCountry,
                  timezone: tz,
                  status: 'ready'
                }
              });
              return;
            }
          } catch {}

          set({
            location: {
              latitude: lat,
              longitude: lon,
              city: defaultCity,
              region: '',
              country: defaultCountry,
              timezone: tz,
              status: 'ready'
            }
          });
        },
        (err) => {
          console.warn('Geolocation prompt skipped/denied:', err.message);
          set((state) => ({
            location: { ...state.location, status: 'fallback' }
          }));
        },
        { timeout: 8000, maximumAge: 60000 }
      );
    }
  }
}));
