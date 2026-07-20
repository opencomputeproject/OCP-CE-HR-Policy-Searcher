import { fireEvent, render, screen } from '@testing-library/react';
import BackToTopButton from './BackToTopButton';

function setScrollY(value) {
  Object.defineProperty(window, 'scrollY', { value, writable: true });
}

describe('BackToTopButton', () => {
  afterEach(() => {
    setScrollY(0);
  });

  it('is hidden at the top of the page', () => {
    setScrollY(0);
    render(<BackToTopButton />);
    expect(screen.queryByRole('button', { name: /back to top/i })).not.toBeInTheDocument();
  });

  it('appears after scrolling down and scrolls back on click', () => {
    setScrollY(0);
    render(<BackToTopButton />);

    setScrollY(1200);
    fireEvent.scroll(window);
    const button = screen.getByRole('button', { name: /back to top/i });

    window.scrollTo = jest.fn();
    fireEvent.click(button);
    expect(window.scrollTo).toHaveBeenCalledWith(
      expect.objectContaining({ top: 0 }),
    );
  });

  it('hides again when scrolled back near the top', () => {
    setScrollY(1200);
    render(<BackToTopButton />);
    fireEvent.scroll(window);
    expect(screen.getByRole('button', { name: /back to top/i })).toBeInTheDocument();

    setScrollY(100);
    fireEvent.scroll(window);
    expect(screen.queryByRole('button', { name: /back to top/i })).not.toBeInTheDocument();
  });
});
