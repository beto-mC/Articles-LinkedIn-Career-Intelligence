/* mAInCharacter — Audio hub behavior
   Adapted from the live "Audio Overview" capsule pattern used across
   main-character.me (play/pause, seek, elapsed/duration, header reveal,
   read-progress). Generalized here to drive three independent players
   on one page instead of a single docked capsule. */
(function () {
  function fmt(s) {
    if (!isFinite(s)) return '--:--';
    s = Math.floor(s);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  var players = Array.prototype.slice.call(document.querySelectorAll('.ao'));

  players.forEach(function (ao) {
    var audio = ao.querySelector('audio');
    var playBtn = ao.querySelector('.ao-play');
    var seek = ao.querySelector('.ao-seek');
    var timeCur = ao.querySelector('.ao-time-current');
    var timeDur = ao.querySelector('.ao-time-duration');
    if (!audio || !playBtn) return;

    audio.addEventListener('loadedmetadata', function () {
      timeDur.textContent = fmt(audio.duration);
      seek.max = audio.duration;
    });
    audio.addEventListener('timeupdate', function () {
      timeCur.textContent = fmt(audio.currentTime);
      if (!seek.matches(':active')) seek.value = audio.currentTime;
    });
    audio.addEventListener('play', function () {
      ao.classList.add('is-playing');
      playBtn.setAttribute('aria-pressed', 'true');
      playBtn.setAttribute('aria-label', 'Pause');
    });
    audio.addEventListener('pause', function () {
      ao.classList.remove('is-playing');
      playBtn.setAttribute('aria-pressed', 'false');
      playBtn.setAttribute('aria-label', 'Play');
    });
    audio.addEventListener('ended', function () { audio.currentTime = 0; });
    audio.addEventListener('error', function () {
      ao.classList.add('is-missing');
      playBtn.disabled = true;
      playBtn.setAttribute('aria-label', 'Audio unavailable');
      timeDur.textContent = 'unavailable';
    }, true);

    playBtn.addEventListener('click', function () {
      players.forEach(function (other) {
        var otherAudio = other.querySelector('audio');
        if (otherAudio && otherAudio !== audio && !otherAudio.paused) otherAudio.pause();
      });
      if (audio.paused) { audio.preload = 'auto'; audio.play().catch(function () {}); if ('mediaSession' in navigator) { navigator.mediaSession.metadata = new MediaMetadata({ title: ao.getAttribute('data-title') || document.title, artist: 'mAInCharacter' }); } }
      else audio.pause();
    });
    /* speed dial (mC Dials stepper): 75%–225% in 25% steps, remembered per visitor */
    var dial = ao.querySelector('.ao-dial');
    var RATES = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25];
    function setRate(r, save) {
      var i = RATES.indexOf(r); if (i < 0) { i = 1; r = 1; }
      audio.defaultPlaybackRate = r; audio.playbackRate = r;
      if (!dial) return;
      dial.querySelector('.ao-rate-v').textContent = r.toFixed(2) + '×';
      dial.setAttribute('aria-label', 'Playback speed, ' + Math.round(r * 100) + ' percent');
      dial.querySelector('[data-dir="-1"]').disabled = i === 0;
      dial.querySelector('[data-dir="1"]').disabled = i === RATES.length - 1;
      [].forEach.call(dial.querySelectorAll('.ao-ticks i'), function (t, k) { t.classList.toggle('on', k <= i); });
      if (save) { try { localStorage.setItem('mc-rate', String(r)); } catch (e) {} }
    }
    var saved = 1; try { saved = parseFloat(localStorage.getItem('mc-rate')) || 1; } catch (e) {}
    setRate(saved, false);
    if (dial) {
      [].forEach.call(dial.querySelectorAll('.ao-step'), function (b) {
        b.addEventListener('click', function () {
          var i = RATES.indexOf(audio.playbackRate) + parseInt(b.getAttribute('data-dir'), 10);
          if (i >= 0 && i < RATES.length) setRate(RATES[i], true);
        });
      });
      [].forEach.call(dial.querySelectorAll('.ao-ticks i'), function (t) {
        t.addEventListener('click', function () { setRate(parseFloat(t.getAttribute('data-r')), true); });
      });
      audio.addEventListener('ratechange', function () {
        if (RATES.indexOf(audio.playbackRate) > -1) setRate(audio.playbackRate, false);
      });
    }
    audio.addEventListener('play', function () { window.mcTrack && window.mcTrack('audio_play', { title: ao.getAttribute('data-title') }); }, { once: true });
    seek.addEventListener('input', function () {
      audio.currentTime = parseFloat(seek.value) || 0;
      timeCur.textContent = fmt(audio.currentTime);
    });
  });

  /* sticky header reveal once the hero scrolls past */
  var head = document.getElementById('siteHead');
  var hero = document.querySelector('.hero');
  if (head && hero && 'IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      head.classList.toggle('show', !entries[0].isIntersecting);
    }, { rootMargin: '-80px 0px 0px 0px', threshold: 0 }).observe(hero);
  } else if (head) {
    head.classList.add('show');
  }

  /* scroll read-progress bar */
  var rp = document.getElementById('readProgress');
  function prog() {
    var h = document.documentElement;
    var max = h.scrollHeight - h.clientHeight;
    rp.style.transform = 'scaleX(' + (max > 0 ? Math.min(1, h.scrollTop / max) : 0) + ')';
  }
  window.addEventListener('scroll', prog, { passive: true });
  prog();

  /* back-to-top */
  var tt = document.getElementById('toTop');
  if (tt) {
    window.addEventListener('scroll', function () {
      var show = window.scrollY > 600;
      tt.hidden = !show;
      tt.classList.toggle('show', show);
    }, { passive: true });
    tt.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
})();

/* Transcript Reveal: condensed at rest, full on tap, tap again to condense,
   and it condenses itself when the reader scrolls away (keeping their place). */
(function () {
  var reveals = Array.prototype.slice.call(document.querySelectorAll('[data-reveal="transcript"]'));
  function set(r, open, keepPlace) {
    var head = r.querySelector('.t-head');
    var before = r.getBoundingClientRect();
    r.classList.toggle('is-open', open);
    head.setAttribute('aria-expanded', String(open));
    head.querySelector('.t-cue-l').textContent = open ? 'Condense' : 'Full transcript';
    // Browsers with scroll anchoring keep the reader's place on their own; others (Safari) get a manual correction.
    if (keepPlace && before.bottom < 0 && !(window.CSS && CSS.supports && CSS.supports('overflow-anchor', 'auto'))) {
      var after = r.getBoundingClientRect();
      window.scrollBy({ top: after.height - before.height, left: 0, behavior: 'instant' });
    }
  }
  reveals.forEach(function (r) {
    r.querySelector('.t-head').addEventListener('click', function () {
      var open = !r.classList.contains('is-open');
      set(r, open, false);
      if (!open && r.getBoundingClientRect().top < 0) r.scrollIntoView({ block: 'start' });
    });
  });
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting && en.target.classList.contains('is-open')) set(en.target, false, true);
      });
    }, { threshold: 0 });
    reveals.forEach(function (r) { io.observe(r); });
  }
  window.addEventListener('beforeprint', function () { reveals.forEach(function (r) { r.classList.add('is-open'); }); });
})();


/* Analytics (consent-gated), downloads, transcript copy, first-visit sonic log */
(function () {
  var ga = document.body.getAttribute('data-ga');
  var consentKey = 'mc-analytics';
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  window.mcTrack = function () {};
  function loadGA() {
    if (!ga || window.gtag) return;
    var sc = document.createElement('script'); sc.async = true; sc.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(ga);
    document.head.appendChild(sc);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', ga, { anonymize_ip: true, allow_google_signals: false, allow_ad_personalization_signals: false });
    window.mcTrack = function (name, params) { window.gtag('event', name, params || {}); };
  }
  var bar = document.getElementById('consent');
  if (ga) {
    var c = read(consentKey);
    if (c === 'yes') loadGA();
    else if (c !== 'no' && bar) bar.hidden = false;
    if (bar) bar.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-consent]'); if (!b) return;
      store(consentKey, b.getAttribute('data-consent')); bar.hidden = true;
      if (b.getAttribute('data-consent') === 'yes') loadGA();
    });
  }
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest('[data-track]');
    if (a) window.mcTrack(a.getAttribute('data-track'), { title: a.getAttribute('data-title'), format: a.getAttribute('data-format') });
  });

  /* copy a whole container (transcript) with the attribution line */
  document.querySelectorAll('.t-copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var body = document.getElementById(btn.getAttribute('data-copy')); if (!body) return;
      var lines = Array.prototype.map.call(body.querySelectorAll('p'), function (p) { return p.innerText.replace(/\s+/g, ' ').trim(); });
      var lic = document.querySelector('.license') ? document.querySelector('.license').innerText.replace(/\s+/g, ' ').trim() : '';
      var text = btn.getAttribute('data-title') + ' — transcript\n\n' + lines.join('\n\n') + '\n\n' + lic + '\n' + location.href;
      var done = function () { var old = btn.textContent; btn.textContent = 'Copied'; btn.classList.add('is-done'); setTimeout(function () { btn.textContent = old; btn.classList.remove('is-done'); }, 1600); window.mcTrack('transcript_copy', { title: btn.getAttribute('data-title') }); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
      else { fallback(text); done(); }
      function fallback(t) { var ta = document.createElement('textarea'); ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) {} ta.remove(); }
    });
  });

  /* sonic logo: a small gold dot, bottom left. Hover or focus opens the waves; pressing plays it
     (pressing again stops it). Optional first-visit play: site.yml sonic_autoplay. An episode
     starting always silences it. */
  var sonic = document.body.getAttribute('data-sonic');
  if (sonic) {
    var au = new Audio(sonic); au.preload = 'none'; au.volume = 0.85;
    var cue = document.createElement('button'); cue.type = 'button'; cue.className = 'sonic-cue';
    cue.setAttribute('aria-label', 'Play the mAInCharacter sonic logo'); cue.setAttribute('aria-pressed', 'false');
    cue.innerHTML = '<svg viewBox="0 0 150 40" aria-hidden="true" focusable="false"><path class="sc-arc sc-a1" d="M39.3 12.6 A10 10 0 0 0 39.3 27.4"/><path class="sc-arc sc-a2" d="M34.6 7.4 A17 17 0 0 0 34.6 32.6"/><path class="sc-arc sc-a3" d="M29.9 2.2 A24 24 0 0 0 29.9 37.8"/><path class="sc-arc sc-a4" d="M25.3 -3.0 A31 31 0 0 0 25.3 43.0"/><line class="sc-bar sc-b1" x1="64.0" y1="14.9" x2="64.0" y2="25.1"/><line class="sc-bar sc-b2" x1="73.2" y1="11.0" x2="73.2" y2="29.0"/><line class="sc-bar sc-b3" x1="82.4" y1="16.7" x2="82.4" y2="23.3"/><line class="sc-bar sc-b4" x1="91.6" y1="7.7" x2="91.6" y2="32.3"/><line class="sc-bar sc-b5" x1="100.8" y1="13.6" x2="100.8" y2="26.4"/><line class="sc-bar sc-b6" x1="110.0" y1="5.0" x2="110.0" y2="35.0"/><line class="sc-bar sc-b7" x1="119.2" y1="14.9" x2="119.2" y2="25.1"/><line class="sc-bar sc-b8" x1="128.4" y1="10.1" x2="128.4" y2="29.9"/><line class="sc-bar sc-b9" x1="137.6" y1="17.6" x2="137.6" y2="22.4"/><circle class="sc-dot" cx="46" cy="20" r="4.6"/></svg>';
    document.body.appendChild(cue);
    var place = function () { cue.classList.toggle('is-raised', !!(bar && !bar.hidden)); };
    place(); if (bar) bar.addEventListener('click', function () { setTimeout(place, 30); });
    var state = function (on) { cue.classList.toggle('is-playing', on); cue.setAttribute('aria-pressed', on ? 'true' : 'false');
      cue.setAttribute('aria-label', on ? 'Stop the sonic logo' : 'Play the mAInCharacter sonic logo'); };
    au.addEventListener('play', function () { state(true); });
    au.addEventListener('pause', function () { state(false); });
    au.addEventListener('ended', function () { state(false); au.currentTime = 0; });
    var tracked = false;
    var go = function () { au.play().then(function () { store('mc-sonic-played', '1'); if (!tracked) { tracked = true; window.mcTrack('sonic_log_play', {}); } }).catch(function () {}); };
    cue.addEventListener('click', function () { if (au.paused) { au.currentTime = 0; go(); } else au.pause(); });
    document.addEventListener('play', function (ev) { if (ev.target !== au && !au.paused) au.pause(); }, true);
    if (document.body.hasAttribute('data-sonic-auto') && !read('mc-sonic-played')) {
      var off = function () { document.removeEventListener('pointerdown', first, true); document.removeEventListener('keydown', first, true); };
      var first = function (ev) {
        off();
        var t = ev.target && ev.target.closest ? ev.target : null;
        if (t && t.closest('.sonic-cue')) return;
        if (t && t.closest('.ao, audio, [data-track="download"]')) { store('mc-sonic-played', '1'); return; }
        go();
      };
      document.addEventListener('pointerdown', first, true); document.addEventListener('keydown', first, true);
    }
  }
})();
