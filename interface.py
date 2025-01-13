import os
import json
import traceback
import logging

from time import time

from othello.game import Game
from othello.move import Move

from options import options
from settings_info import settings

from engine.engine import *

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Runner:
    def __init__(self):
        self.game = Game
        self.initialized = False
        self.playing = False

        # Settings
        self.init_settings()

        if self.settings.get('auto_start_game'):
            self.new_game()
    
    def exit(self):
        with open('settings.json', 'w') as f:
            json.dump(self.settings, f)
        quit()

    def init_settings(self):
        if os.path.exists('settings.json'):
            with open('settings.json') as f:
                self.settings = json.load(f)
        else:
            self.settings = {key: settings[key].get('default') for key in settings.keys()}

    def enable(self, **kwargs):
        for key in self.settings.keys():
            if kwargs.get(key, False):
                self.settings[key] = True
    
    def disable(self, **kwargs):
        for key in self.settings.keys():
            if kwargs.get(key, False):
                self.settings[key] = False

    def new_game(self, **kwargs):
        if kwargs.get('w', False):
            color = 'w'
        else:
            color = 'b'

        pgn = kwargs.get('pgn', None)
        if pgn is not None:
            try:
                with open(pgn) as f:
                    pgn = f.read()
            except Exception as e:
                print(e)

        fen = kwargs.get('fen', None)
        self.game = Game(pgn, fen, color)
        self.initialized = True
        self.playing = True

        print('New game started.')
        self.auto_display()

    def ai_move(self, **kwargs):
        if not self.initialized:
            print('Game not initialized. Try using \'new-game\' first.')
            return
        if not self.playing:
            print('Game over. Use \'new-game\' to start a new game.')
            return
        
        depth = int(kwargs.get('depth', 10))
        time_limit = float(kwargs.get('time', 5.0))
        start_time = time()
        result, max_depth = ai_move_iterative(self.game.board, self.game.color, depth, time_limit)
        execution_time = time() - start_time

        print(f'The computer on depth:{max_depth} recommends {result[0]}\nEvaluation: {str(result[1])[:5]}\nExecution time: {str(execution_time)[:3]} seconds')

    def auto_display(self):
        if self.settings.get('auto_display_board'):
            self.game.print_board()
        if self.settings.get('auto_display_fen'):
            self.game.print_fen()
        if self.settings.get('auto_display_pgn'):
            self.game.print_pgn()

    def print_result(self):
        if self.game.result is None:
            print('No result to print.')
        else:
            print(f'{self.game.result} {self.game.black_count}-{self.game.white_count}')

    def move(self, **kwargs):
        if not self.initialized:
            print('Game not initialized. Try using \'new-game\' first.')
            return
        if not self.playing:
            print('Game over. Use \'new-game\' to start a new game.')
            return
        
        if 'color' in kwargs.keys():
            for key in kwargs.keys():
                if key == 'color':
                    break
                result = self.game.make_move(Move(key, kwargs.get('color')))
        else:
            for key in kwargs.keys():
                result = self.game.make_move(key)
        if not result:
            print('Illegal move')
            return
        if self.game.game_over:
            self.game_over()
        self.auto_display()
        print(f'{['Black', 'White']['bw'.find(self.game.color)]} to move...')

    def resign(self, **kwargs):
        if not self.initialized:
            print('Game not initialized. Try using \'new-game\' first.')
            return
        if 'color' in kwargs.keys():
            winner = ['black', 'white']['wb'.find(kwargs.get('color'))]
        else:
            winner = ['black', 'white']['wb'.find(self.game.color)]
        self.game.result = f'{winner} wins by resignation'
        self.playing = False
        self.print_result()
        self.auto_display()

    def draw(self, **kwargs):
        if not self.initialized:
            print('Game not initialized. Try using \'new-game\' first.')
            return
        self.game.result = 'draw'
        self.playing = False
        self.print_result()
        self.auto_display()
    
    def game_over(self):
        print('Game over. ', end=None)
        self.playing = False
        self.print_result()
        self.auto_display()

    def display(self, **kwargs):
        if not self.initialized:
            print('Game not initialized. Try using \'new-game\' first.')
            return
        if kwargs.get('board', False):
            self.game.print_board()
        if kwargs.get('fen', False):
            self.game.print_fen()
        if kwargs.get('pgn', False):
            self.game.print_pgn()


def print_help(command:str=None):
    s = ''
    if command is None:
        for key in options.keys():
            usage = options[key].get('usage')
            s += f'{key}:\n\tusage: {usage}\n'

            arguments = options[key].get('arguments')
            if len(arguments) == 0:
                continue
            for argument in arguments:
                label = argument.get('label')
                usage = argument.get('usage')
                s += f'\t {label}:\t{usage}\n'
    print(s)

def print_settings(settings_dict):
    s = ''
    for key in settings.keys():
        s += f'{key}\n'
        s += f'\tvalue:    {settings_dict.get(key)}\n'
        s += f'\tfunction: {settings[key].get('hint')}\n'
    print(s)

print('Welcome to the python-othello interface!\nType \'help\' to learn how to use the program.')
runner = Runner()
while True:
    text = input('> ')
    command = text.split()
    key = command[0]
    args = command[1:]

    try:
        if key == 'help':
            print_help()
            continue
        elif key == 'settings':
            print_settings(runner.settings)
            continue
        else:
            func_name = options[key]['function']
            func = getattr(runner, options[key]['function'])
    except Exception as e:
        print(f'{key} is not a valid command.')
        continue

    kwargs = {}
    index = 0
    while index < len(args):
        arg_value = True
        if args[index].find('-') == 0: # key
            if args[index].find('--') == 0: # arg is string
                arg_value = args[index+1]
        
        arg_name = args[index].lstrip('-')
        kwargs[arg_name] = arg_value

        if args[index].find('--') == 0:
            index += 2
        else:
            index += 1
    try:
        func(**kwargs)
    except Exception as e:
        logger.debug(traceback.format_exc())
    