import type { Transition, Variants } from 'framer-motion';

export const ease = [0.2, 0.7, 0.2, 1] as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease } },
};

export const staggerContainer = (gap = 0.08, delay = 0): Variants => ({
  hidden: {},
  show:   { transition: { staggerChildren: gap, delayChildren: delay } },
});

export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease } },
  exit:    { opacity: 0, y: -4, transition: { duration: 0.15, ease } },
};

export const spring: Transition = { type: 'spring', stiffness: 280, damping: 30 };
