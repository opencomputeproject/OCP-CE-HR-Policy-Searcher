import * as React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';

const cards = [
  {
    id: 'standard',
    title: 'Standard',
    description: 'Scan known domains with normal settings.',
    tint: '#f8fafc',
    hoverTint: '#f1f5f9',
    selectedTint: '#dbe4ef',
    selectedHoverTint: '#d1d9e3',
    border: '#a3b1da',
  },
  {
    id: 'discover',
    title: 'Discover',
    description: 'Find new domains (URLs).',
    tint: '#f8fafc',
    hoverTint: '#f1f5f9',
    selectedTint: '#dbe4ef',
    selectedHoverTint: '#d1d9e3',
    border: '#a3b1da',
  },
  {
    id: 'deep',
    title: 'Deep',
    description: 'Scan every domain more thoroughly.',
    tint: '#fbfaf8',
    hoverTint: '#e0c7ea',
    selectedTint: '#e0d6e4',
    selectedHoverTint: '#c0a5d0',
    border: '#c377e2',
  },
];

function ModeSelector({ value = 'standard', onChange }) {
  return (
    <Box
      sx={{
        width: '100%',
        display: 'grid',
        gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
        gap: 1.5,
        minWidth: '150px',
        overflow: 'anywhere',
      }}
    >
      {cards.map((card) => {
        const isSelected = value === card.id;

        return (
          <Card
            key={card.id}
            variant="outlined"
            sx={{
              minWidth: 0,
              borderColor: isSelected ? '#64748b' : card.border,
              backgroundColor: isSelected ? card.selectedTint : card.tint,
              boxShadow: isSelected ? 'inset 0 0 0 1px #64748b' : 'none',
              transition: 'border-color 120ms ease, background-color 120ms ease',
            }}
          >
            <CardActionArea
              disableRipple
              disableTouchRipple
              focusRipple={false}
              onClick={() => onChange?.(card.id)}
              aria-pressed={isSelected}
              sx={{
                height: '100%',
                transition: 'none',
                '& .MuiCardActionArea-focusHighlight': {
                  display: 'none',
                },
                '&:hover': {
                  backgroundColor: isSelected ? card.selectedHoverTint : card.hoverTint,
                },
              }}
            >
              <CardContent sx={{ height: '100%', minWidth: 0, padding: 1.5 }}>
                <Typography
                  variant="h5"
                  component="div"
                  sx={{
                    color: isSelected ? '#0f172a' : '#334155',
                    fontSize: 'clamp(1rem, 1.6vw, 1.5rem)',
                    overflowWrap: 'anywhere',
                  }}
                >
                  {card.title}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color: isSelected ? '#334155' : '#64748b',
                    overflowWrap: 'anywhere',
                  }}
                >
                  {card.description}
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        );
      })}
    </Box>
  );
}

export default ModeSelector;
