import React from 'react';

const originalCreateElement = React.createElement;
React.createElement = function patchedCreateElement(type, props, ...children) {
  try {
    const typeName = (type && (type.displayName || type.name)) || '';
    if (typeof typeName === 'string' && typeName.includes('TextField')) {
      props = props || {};
      if (!Object.prototype.hasOwnProperty.call(props, 'autoComplete')) {
        props = { ...props, autoComplete: 'off' };
      }
    }
  } catch (e) {
    // swallow errors to avoid breaking app rendering
  }
  return originalCreateElement(type, props, ...children);
};

export default null;
