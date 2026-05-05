import { render, screen } from '@testing-library/react';
import App from './App';

test('renders app heading', () => {
  render(<App />);
  const linkElement = screen.getByText(/OCP Policy Searcher/i);
  expect(linkElement).toBeInTheDocument();
});
