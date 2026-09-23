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
