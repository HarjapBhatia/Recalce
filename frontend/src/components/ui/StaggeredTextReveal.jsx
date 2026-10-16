import React from 'react';
import { motion } from 'framer-motion';

export function StaggeredTextReveal({ text, className }) {
  const words = text.split(" ");
  
  return (
    <div className={className}>
      {words.map((word, idx) => (
        <motion.span
          key={idx}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.25,
            delay: idx * 0.04,
            ease: "easeOut",
          }}
          style={{ display: "inline-block", marginRight: "0.25em" }}
        >
          {word}
        </motion.span>
      ))}
    </div>
  );
}
