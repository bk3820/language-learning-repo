/* Click-to-pronounce: uses the browser's Web Speech API (no API key needed).
   Works on all pages — clicks any table cell to hear it spoken in French. */
(function () {
  if (!('speechSynthesis' in window)) return;

  function speak(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'fr-FR';
    utterance.rate = 0.85;
    speechSynthesis.cancel(); // stop any currently playing audio
    speechSynthesis.speak(utterance);
  }

  function isDate(text) {
    return /^\d{4}-\d{2}-\d{2}$/.test(text);
  }

  function addPronunciationToCell(td) {
    const text = td.textContent.trim();
    if (!text || isDate(text)) return;

    td.classList.add('pronounceable');
    td.setAttribute('title', '🔊 Click to hear pronunciation');

    td.addEventListener('click', function (e) {
      e.stopPropagation();
      speak(text);

      // brief visual feedback
      td.classList.add('pronouncing');
      setTimeout(() => td.classList.remove('pronouncing'), 600);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('table td').forEach(addPronunciationToCell);
  });
})();
