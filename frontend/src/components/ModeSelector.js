import * as React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import CardActionArea from '@mui/material/CardActionArea';

const cards = [
  {
    id: 'discover',
    title: 'Discover',
    description: 'Discover new policies and regulations.',
  },
  {
    id: 'deep',
    title: 'Deep',
    description: 'Perform a deep dive into policy details.',
  },
  {
    id: 'interactive',
    title: 'Interactive',
    description: 'Interact with policies in real-time.',
  },
];

function ModeSelector({ value = 'discover', onChange }) {
  return (
    <Box
      sx={{
        width: '100%',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(min(150px, 100%), 1fr))',
        gap: 2,
      }}
>
      {cards.map((card) => {
        const isSelected = value === card.id;

        return (
        <Card
          key={card.id}
          variant="outlined"
          sx={{
            borderColor: isSelected ? 'primary.main' : 'divider',
            backgroundColor: isSelected ? 'action.selected' : 'background.paper',
            transition: 'border-color 120ms ease, background-color 120ms ease',
          }}
        >
          <CardActionArea
            disableRipple
            disableTouchRipple
            focusRipple={false}
            onClick={() => onChange?.(card.id)}
            data-active={isSelected ? '' : undefined}
            sx={{
              height: '100%',
              transition: 'none',
              '& .MuiCardActionArea-focusHighlight': {
                display: 'none',
              },
              '&[data-active]': {
                '&:hover': {
                  backgroundColor: 'action.selectedHover',
                },
              },
            }}
          >
            <CardContent sx={{ height: '100%' }}>
              <Typography variant="h5" component="div">
                {card.title}
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
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
