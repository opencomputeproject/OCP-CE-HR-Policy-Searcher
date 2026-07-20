import React, { useEffect, useState } from 'react';
import './BackToTopButton.css';

// Appears once the page has scrolled past roughly one viewport, so it never
// covers anything on a short page or at the top.
const SHOW_AFTER_PX = 600;

function BackToTopButton() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setIsVisible(window.scrollY > SHOW_AFTER_PX);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!isVisible) return null;

  const handleClick = () => {
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
  };

  return (
    <button
      type="button"
      className="back-to-top"
      onClick={handleClick}
      aria-label="Back to top"
      title="Back to top"
    >
      <span aria-hidden="true">&uarr;</span> Top
    </button>
  );
}

export default BackToTopButton;
