'use strict';

// Bump this on every deploy that changes a cached file (keep in step with
// APP_VERSION in index.html). Versioning the cache name is what lets
// `activate` safely wipe every old cache without touching localStorage -
// the Cache Storage API and localStorage are entirely separate stores, so
// nothing here can ever reach her workout log.
var CACHE_VERSION = '1.2.0';
var CACHE_NAME = 'coach-' + CACHE_VERSION;

// Must match VOICE_PACK_DIR in index.html - no build step ties these
// together, so keep them in sync by hand when the chosen voice changes.
var VOICE_PACK_DIR = 'he-IL-Chirp3-HD-Callirrhoe';

var APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-192-maskable.png',
  './icons/icon-512-maskable.png',
  './voice-manifest.json'
];

self.addEventListener('install', function(event){
  event.waitUntil(
    fetch('./voice-manifest.json').then(function(resp){ return resp.json(); }).then(function(manifest){
      // Every voice clip ships with the app shell so the coach works fully
      // offline from the first open - matches how the rest of the app is
      // cached, not fetched lazily on first use.
      var audioUrls = Object.keys(manifest).map(function(key){
        return './audio/' + VOICE_PACK_DIR + '/' + key.split('.').join('/') + '.mp3';
      });
      return caches.open(CACHE_NAME).then(function(cache){
        return cache.addAll(APP_SHELL.concat(audioUrls));
      });
    })
  );
  // Deliberately no self.skipWaiting() here: a new service worker should
  // sit in "waiting" until every open tab/PWA window has been fully closed
  // and reopened, so an update can never hot-swap the app shell out from
  // under a workout in progress. The one exception is the explicit "force
  // update" button in Settings, which asks this waiting worker to take
  // over via the message listener below.
});

self.addEventListener('activate', function(event){
  event.waitUntil(
    caches.keys().then(function(names){
      return Promise.all(
        names.filter(function(name){ return name !== CACHE_NAME; })
             .map(function(name){ return caches.delete(name); })
      );
    }).then(function(){
      return self.clients.claim();
    })
  );
});

self.addEventListener('message', function(event){
  if(event.data === 'SKIP_WAITING'){
    self.skipWaiting();
  }
});

self.addEventListener('fetch', function(event){
  if(event.request.method !== 'GET') return;
  var url = new URL(event.request.url);
  if(url.origin !== self.location.origin) return; // never intercept the optional online-only features (share/YouTube link)

  event.respondWith(
    caches.match(event.request).then(function(cached){
      var networkFetch = fetch(event.request).then(function(response){
        if(response && response.ok){
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function(cache){ cache.put(event.request, copy); });
        }
        return response;
      }).catch(function(){
        return cached; // offline and nothing new to offer - fall back to whatever we had
      });
      // Cache-first: serve instantly if we have it, refresh the cache quietly in the background.
      return cached || networkFetch;
    })
  );
});
