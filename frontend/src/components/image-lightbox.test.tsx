import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ImageLightbox } from './image-lightbox';

const image = { url: '/api/library/assets/1/file', name: 'image-1.png' };

it('opens the image large, offers download and closes on Escape', () => {
  render(<ImageLightbox image={image} />);
  expect(screen.getByRole('button', { name: 'Tải image-1.png' })).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Xem lớn image-1.png' }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Tải ảnh về' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Mở ảnh trong tab mới' })).toHaveAttribute('href', image.url);

  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
