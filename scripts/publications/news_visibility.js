/* Dates are calendar dates in Stockholm, regardless of the visitor's timezone. */
(() => {
  const formatter = new Intl.DateTimeFormat('en', {
    timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit'
  });
  function update() {
    const parts = formatter.formatToParts(new Date());
    const value = name => parts.find(part => part.type === name).value;
    const today = `${value('year')}-${value('month')}-${value('day')}`;
    document.querySelectorAll('.news-item[data-news-pub][data-news-close]').forEach(item => {
      item.hidden = !(item.dataset.newsPub <= today && today <= item.dataset.newsClose);
    });
  }
  function start() {
    update();
    // Also update a page left open across midnight or resumed after being suspended.
    window.setInterval(update, 60000);
    window.addEventListener('pageshow', update);
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', update);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})();
