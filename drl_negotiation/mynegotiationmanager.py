'''
My NegotiationManager
'''
####
# package which Used for Test 
from scml import MovingRangeNegotiationManager
####
from typing import List, Dict, Optional, Any

from scml import NegotiationManager, IndependentNegotiationsManager
from negmas import AgentMechanismInterface, Negotiator, Issue, SAONegotiator

from .negotiator import MyDRLNegotiator

class MyNegotiationManager(IndependentNegotiationsManager):
    r"""
    TODO:
    """
    def __init__(
        self, 
        *args, 
        negotiator_type = MyDRLNegotiator,
        negotiator_params = None,
        **kwargs, 
    ):
        super().__init__(negotiator_type = MyDRLNegotiator, negotiator_params = None, *args, **kwargs)


    def negotiator(self, is_seller: bool, issues=None, outcomes=None) -> MyDRLNegotiator:
        pass