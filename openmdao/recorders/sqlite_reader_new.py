"""
Definition of the SqliteCaseReader.
"""
from __future__ import print_function, absolute_import

from copy import deepcopy
import re
import sys
import sqlite3
from collections import OrderedDict

from six import PY2, PY3, reraise, iteritems
from six.moves import range

import numpy as np

from openmdao.recorders.base_case_reader import BaseCaseReader
from openmdao.recorders.case import DriverCase, SystemCase, SolverCase, ProblemCase, \
    PromotedToAbsoluteMap, DriverDerivativesCase
from openmdao.recorders.cases import BaseCases
from openmdao.utils.record_util import check_valid_sqlite3_db, json_to_np_array, convert_to_np_array
from openmdao.recorders.sqlite_recorder import blob_to_array, format_version
from openmdao.utils.write_outputs import write_outputs

from pprint import pprint
import json

if PY2:
    import cPickle as pickle
    from openmdao.utils.general_utils import json_loads_byteified as json_loads
elif PY3:
    import pickle
    from json import loads as json_loads


_DEFAULT_OUT_STREAM = object()

# Regular expression used for splitting iteration coordinates.
_coord_split_re = re.compile('\|\\d+\|*')


class Case(object):
    """
    Case wraps the data from a single iteration of a recording to make it more easily accessible.

    Attributes
    ----------
    source : str
        The unique id of the system/solver/driver/problem that did the recording.
    iteration_coordinate : str
        The full unique identifier for this iteration.
    timestamp : float
        Time of execution of the case.
    parent_iteration : str
        The full unique identifier for the parent this iteration.
    parent_iteration : list
        The full unique identifiers for children of this iteration.
    outputs : PromotedToAbsoluteMap
        Map of outputs to values recorded.
    inputs : PromotedToAbsoluteMap or None
        Map of inputs to values recorded (None if not recorded).
    residuals : PromotedToAbsoluteMap or None
        Map of outputs to residuals recorded (None if not recorded).
    jacobian : PromotedToAbsoluteMap or None
        Map of (output, input) to derivatives recorded (None if not recorded).
    abs_tol : float or None
        Absolute tolerance (None if not recorded).
    rel_tol : float or None
        Relative tolerance (None if not recorded).
    success : str
        Success flag for the case.
    msg : str
        Message associated with the case.
    """

    def __init__(self, source, iteration_coordinate, timestamp, success, msg,
                 outputs, inputs=None, residuals=None, jacobian=None):
        pass

    def get_design_variables(self, scaled=True, use_indices=True):
        """
        Get the values of the design variables, as seen by the driver, for this case.

        Parameters
        ----------
        scaled : bool
            The unique id of the system/solver/driver/problem that did the recording.
        use_indices : bool
            The full unique identifier for this iteration.

        Returns
        -------
        dict
            The values of the design variables as seen by the driver.
        """
        pass

    def get_constraints(self, scaled=True, use_indices=True):
        """
        Get the values of the constraints, as seen by the driver, for this case.

        Parameters
        ----------
        scaled : bool
            The unique id of the system/solver/driver/problem that did the recording.
        use_indices : bool
            The full unique identifier for this iteration.

        Returns
        -------
        dict
            The values of the constraints as seen by the driver.
        """
        pass

    def get_objectives(self, scaled=True, use_indices=True):
        """
        Get the values of the objectives, as seen by the driver, for this case.

        Parameters
        ----------
        scaled : bool
            The unique id of the system/solver/driver/problem that did the recording.
        use_indices : bool
            The full unique identifier for this iteration.

        Returns
        -------
        dict
            The values of the objectives as seen by the driver.
        """
        pass

    def get_responses(self, scaled=True, use_indices=True):
        """
        Get the values of the responses, as seen by the driver, for this case.

        Parameters
        ----------
        scaled : bool
            The unique id of the system/solver/driver/problem that did the recording.
        use_indices : bool
            The full unique identifier for this iteration.

        Returns
        -------
        dict
            The values of the responses as seen by the driver.
        """
        pass

    def list_inputs(self,
                    values=True,
                    units=False,
                    hierarchical=True,
                    print_arrays=False,
                    out_stream=_DEFAULT_OUT_STREAM):
        """
        Return and optionally log a list of input names and other optional information.

        If the model is parallel, only the local variables are returned to the process.
        Also optionally logs the information to a user defined output stream. If the model is
        parallel, the rank 0 process logs information about all variables across all processes.

        Parameters
        ----------
        values : bool, optional
            When True, display/return input values. Default is True.
        units : bool, optional
            When True, display/return units. Default is False.
        hierarchical : bool, optional
            When True, human readable output shows variables in hierarchical format.
        print_arrays : bool, optional
            When False, in the columnar display, just display norm of any ndarrays with size > 1.
            The norm is surrounded by vertical bars to indicate that it is a norm.
            When True, also display full values of the ndarray below the row. Format is affected
            by the values set with numpy.set_printoptions
            Default is False.
        out_stream : file-like object
            Where to send human readable output. Default is sys.stdout.
            Set to None to suppress.

        Returns
        -------
        list
            list of input names and other optional information about those inputs
        """
        pass

    def list_outputs(self,
                     explicit=True, implicit=True,
                     values=True,
                     prom_name=False,
                     residuals=False,
                     residuals_tol=None,
                     units=False,
                     shape=False,
                     bounds=False,
                     scaling=False,
                     hierarchical=True,
                     print_arrays=False,
                     out_stream=_DEFAULT_OUT_STREAM):
        """
        Return and optionally log a list of output names and other optional information.

        If the model is parallel, only the local variables are returned to the process.
        Also optionally logs the information to a user defined output stream. If the model is
        parallel, the rank 0 process logs information about all variables across all processes.

        Parameters
        ----------
        explicit : bool, optional
            include outputs from explicit components. Default is True.
        implicit : bool, optional
            include outputs from implicit components. Default is True.
        values : bool, optional
            When True, display/return output values. Default is True.
        prom_name : bool, optional
            When True, display/return the promoted name of the variable.
            Default is False.
        residuals : bool, optional
            When True, display/return residual values. Default is False.
        residuals_tol : float, optional
            If set, limits the output of list_outputs to only variables where
            the norm of the resids array is greater than the given 'residuals_tol'.
            Default is None.
        units : bool, optional
            When True, display/return units. Default is False.
        shape : bool, optional
            When True, display/return the shape of the value. Default is False.
        bounds : bool, optional
            When True, display/return bounds (lower and upper). Default is False.
        scaling : bool, optional
            When True, display/return scaling (ref, ref0, and res_ref). Default is False.
        hierarchical : bool, optional
            When True, human readable output shows variables in hierarchical format.
        print_arrays : bool, optional
            When False, in the columnar display, just display norm of any ndarrays with size > 1.
            The norm is surrounded by vertical bars to indicate that it is a norm.
            When True, also display full values of the ndarray below the row. Format  is affected
            by the values set with numpy.set_printoptions
            Default is False.
        out_stream : file-like
            Where to send human readable output. Default is sys.stdout.
            Set to None to suppress.

        Returns
        -------
        list
            list of output names and other optional information about those outputs
        """
        pass


class CaseReader():
    """
    A CaseReader specific to files created with SqliteRecorder.

    Parameters
    ----------
    filename : str
        The path to the filename containing the recorded data.

    Attributes
    ----------
    format_version : int
        The version of the format assumed when loading the file.
    system_metadata : dict
        Metadata about each system in the recorded model, including options and scaling factors.
    problem_metadata : dict
        Metadata about the problem, including the system hierachy and connections.
    """

    def __init__(self, filename, pre_load=False):
        """
        Initialize.

        Parameters
        ----------
        filename : str
            The path to the filename containing the recorded data.
        pre_load : bool
            If True, load all the data into memory during initialization.
        """
        pass

    def get_cases(self, source, recurse=True, flat=False):
        """
        Initialize.

        Parameters
        ----------
        source : {'problem', 'driver', iteration_coordinate}
            Identifies which cases to return. 'iteration_coordinate' can refer to
            a system or a solver hierarchy location. Defaults to 'problem'.
        recurse : bool, optional
            If True, will enable iterating over all successors in case hierarchy
            rather than just the direct children. Defaults to True.
        flat : bool
            If True, return a flat dictionary rather than a nested dictionary.

        Returns
        -------
        dict
            The cases identified by the source
        """
        pass

    def get_case(self, id, recurse=True):
        """
        Initialize.

        Parameters
        ----------
        id : str
            The unique identifier of the case to return.
        recurse : bool, optional
            If True, will enable iterating over all successors in case hierarchy
            rather than just the direct children. Defaults to True.

        Returns
        -------
        dict
            The case identified by the is
        """
        pass

    def list_sources(self):
        """
        List of all the different recording sources for which there is recorded data.

        Returns
        -------
        list
            One or more of: `problem`, `driver`, `<component hierarchy location>`,
            `<solver hierarchy location>`
        """
        pass

    def list_source_vars(self, source):
        """
        List of all the different recording sources for which there is recorded data.

        Parameters
        ----------
        source : {'problem', 'driver', iteration_coordinate}
            Identifies which cases to return. 'iteration_coordinate' can refer to
            a system or a solver hierarchy location. Defaults to 'problem'.

        Returns
        -------
        dict
            {'inputs':[list of keys], 'outputs':[list of keys]}. Does not recurse.
        """
        pass


class SqliteCaseReader(BaseCaseReader):
    """
    A CaseReader specific to files created with SqliteRecorder.

    Parameters
    ----------
    filename : str
        The path to the filename containing the recorded data.

    Attributes
    ----------
    format_version : int
        The version of the format assumed when loading the file.
    output2meta : dict
        Dictionary mapping output variables to their metadata
    input2meta : dict
        Dictionary mapping input variables to their metadata
    _abs2meta : dict
        Dictionary mapping variables to their metadata
    _abs2prom : {'input': dict, 'output': dict}
        Dictionary mapping absolute names to promoted names.
    _prom2abs : {'input': dict, 'output': dict}
        Dictionary mapping promoted names to absolute names.
    _var_settings : dict
        Dictionary mapping absolute variable names to variable settings.
    """

    def __init__(self, filename, pre_load=False):
        """
        Initialize.

        Parameters
        ----------
        filename : str
            The path to the filename containing the recorded data.
        pre_load : bool
            If True, load all the data into memory during initialization.
        """
        super(SqliteCaseReader, self).__init__(filename)

        check_valid_sqlite3_db(filename)

        with sqlite3.connect(self.filename) as con:
            con.row_factory = sqlite3.Row

            cur = con.cursor()
            cur.execute('select * from metadata')

            row = cur.fetchone()

            self.format_version = row['format_version']

            if self.format_version >= 4:
                self._var_settings = json_loads(row['var_settings'])
            else:
                self._var_settings = None

            if self.format_version >= 3:
                self._abs2prom = json_loads(row['abs2prom'])
                self._prom2abs = json_loads(row['prom2abs'])
                self._abs2meta = json_loads(row['abs2meta'])

                # need to convert bounds to numpy arrays
                for name, meta in iteritems(self._abs2meta):
                    if 'lower' in meta:
                        meta['lower'] = convert_to_np_array(meta['lower'], name, meta['shape'])
                    if 'upper' in meta:
                        meta['upper'] = convert_to_np_array(meta['upper'], name, meta['shape'])

            elif self.format_version in (1, 2):
                abs2prom = row['abs2prom']
                prom2abs = row['prom2abs']
                abs2meta = row['abs2meta']

                if PY2:
                    self._abs2prom = pickle.loads(str(abs2prom))
                    self._prom2abs = pickle.loads(str(prom2abs))
                    self._abs2meta = pickle.loads(str(abs2meta))

                if PY3:
                    try:
                        self._abs2prom = pickle.loads(abs2prom)
                        self._prom2abs = pickle.loads(prom2abs)
                        self._abs2meta = pickle.loads(abs2meta)
                    except TypeError:
                        # Reading in a python 2 pickle recorded pre-OpenMDAO 2.4.
                        self._abs2prom = pickle.loads(abs2prom.encode())
                        self._prom2abs = pickle.loads(prom2abs.encode())
                        self._abs2meta = pickle.loads(abs2meta.encode())

        con.close()

        self.output2meta = PromotedToAbsoluteMap(self._abs2meta, self._prom2abs, self._abs2prom, 1)
        self.input2meta = PromotedToAbsoluteMap(self._abs2meta, self._prom2abs, self._abs2prom, 0)

        self._load()

        if pre_load:
            self.load_cases()

    def _load(self):
        """
        Load data from the sqlite database file.

        Load the metadata from the sqlite file, populating the
        `format_version`, `parameters`, and `unknowns` attributes of this CaseReader.

        The `iterations` table is read to load the keys which identify
        the individual cases/iterations from the recorded file.
        """
        self.driver_cases = DriverCases(self.filename, self.format_version, self._abs2prom,
                                        self._abs2meta, self._prom2abs, self._var_settings)
        self.driver_derivative_cases = DriverDerivativeCases(self.filename, self.format_version,
                                                             self._abs2prom, self._abs2meta,
                                                             self._prom2abs)
        self.system_cases = SystemCases(self.filename, self.format_version, self._abs2prom,
                                        self._abs2meta, self._prom2abs)
        self.solver_cases = SolverCases(self.filename, self.format_version, self._abs2prom,
                                        self._abs2meta, self._prom2abs)
        self.problem_cases = ProblemCases(self.filename, self.format_version, self._abs2prom,
                                          self._abs2meta, self._prom2abs)

        if self.format_version in range(1, format_version + 1):
            with sqlite3.connect(self.filename) as con:

                # Read in iterations from Drivers, Systems, Problems, and Solvers
                iter_query = "SELECT iteration_coordinate FROM %s ORDER BY id ASC"

                cur = con.cursor()
                cur.execute(iter_query % "driver_iterations")
                rows = cur.fetchall()
                self.driver_cases._case_keys = [coord[0] for coord in rows]
                self.driver_cases.num_cases = len(self.driver_cases._case_keys)

                try:
                    cur.execute(iter_query % "driver_derivatives")
                    rows = cur.fetchall()
                    dcase = self.driver_derivative_cases
                    dcase._case_keys = [coord[0] for coord in rows]
                    dcase.num_cases = len(dcase._case_keys)
                except sqlite3.OperationalError:
                    # Cases recorded in version 1 won't have a 'derivatives' table.
                    if self.format_version >= 2:
                        reraise(*sys.exc_info())

                cur.execute(iter_query % "system_iterations")
                rows = cur.fetchall()
                self.system_cases._case_keys = [coord[0] for coord in rows]
                self.system_cases.num_cases = len(self.system_cases._case_keys)

                cur.execute(iter_query % "solver_iterations")
                rows = cur.fetchall()
                self.solver_cases._case_keys = [coord[0] for coord in rows]
                self.solver_cases.num_cases = len(self.solver_cases._case_keys)

                try:
                    cur.execute("SELECT case_name FROM problem_cases ORDER BY id ASC")
                    rows = cur.fetchall()
                    self.problem_cases._case_keys = [coord[0] for coord in rows]
                    self.problem_cases.num_cases = len(self.problem_cases._case_keys)

                except sqlite3.OperationalError:
                    # Cases recorded in some early iterations of version 1 won't have
                    # the 'problem_cases' table.
                    if self.format_version >= 2:
                        reraise(*sys.exc_info())

                # Read in metadata for Drivers, Systems, and Solvers
                cur.execute("SELECT model_viewer_data FROM driver_metadata")
                row = cur.fetchone()
                if row is not None:
                    if self.format_version >= 3:
                        self.driver_metadata = json_loads(row[0])
                    elif self.format_version in (1, 2):
                        if PY2:
                            self.driver_metadata = pickle.loads(str(row[0]))
                        if PY3:
                            self.driver_metadata = pickle.loads(row[0])

                cur.execute("SELECT id, scaling_factors, component_metadata FROM system_metadata")
                for row in cur:
                    id = row[0]
                    self.system_metadata[id] = {}

                    if PY2:
                        self.system_metadata[id]['scaling_factors'] = pickle.loads(str(row[1]))
                        self.system_metadata[id]['component_options'] = pickle.loads(str(row[2]))
                    if PY3:
                        self.system_metadata[id]['scaling_factors'] = pickle.loads(row[1])
                        self.system_metadata[id]['component_options'] = pickle.loads(row[2])

                cur.execute("SELECT id, solver_options, solver_class FROM solver_metadata")
                for row in cur:
                    id = row[0]
                    if PY2:
                        solver_options = pickle.loads(str(row[1]))
                    if PY3:
                        solver_options = pickle.loads(row[1])
                    solver_class = row[2]
                    self.solver_metadata[id] = {
                        'solver_options': solver_options,
                        'solver_class': solver_class,
                    }
            con.close()
        else:
            raise ValueError('SQliteCaseReader encountered an unhandled '
                             'format version: {0}'.format(self.format_version))

    def load_cases(self):
        """
        Load all driver, solver, and system cases into memory.
        """
        self.driver_cases.load_cases()
        self.solver_cases.load_cases()
        self.system_cases.load_cases()
        self.problem_cases.load_cases()

    def get_cases(self, source='problem', recurse=True, flat=False):
        """
        Allow one to iterate over the driver and solver cases.

        Generator giving Driver and/or Solver cases in order.

        Parameters
        ----------
        source : {'problem', 'driver', iteration_coordinate}
            Identifies which cases to return. 'iteration_coordinate' can refer to
            a system or a solver hierarchy location. Defaults to 'problem'.
        recurse : bool, optional
            If True, will enable iterating over all successors in case hierarchy
            rather than just the direct children. Defaults to False.
        """
        if not isinstance(source, str):
            raise TypeError("'source' parameter must be a string.")

        elif source == 'problem':
            print('yielding problem cases...')
            for case in self.problem_cases.cases():
                yield case

        elif source == 'driver':
            for case in self.driver_cases.cases():
                yield case

        else:
            iter_coord = source

            driver_iter = []
            solver_iter = []
            with sqlite3.connect(self.filename) as con:
                cur = con.cursor()
                cur.execute("SELECT iteration_coordinate FROM driver_iterations "
                            "ORDER BY counter ASC")
                driver_iter = cur.fetchall()

                cur.execute("SELECT iteration_coordinate, counter FROM solver_iterations "
                            "ORDER BY counter ASC")
                solver_iter = cur.fetchall()
            con.close()

            split_iter_coord = _coord_split_re.split(iter_coord) if iter_coord is not '' else []

            # grab an array of possible lengths of coordinates
            coord_lengths = [2]  # start with 2 because that is the length of driver iter coords
            for s in solver_iter:
                s_len = len(_coord_split_re.split(s[0]))
                if s_len not in coord_lengths:
                    coord_lengths.append(s_len)
            coord_lengths = sorted(coord_lengths)

            # grab full set of cases to iterate over
            iter_set = self._find_child_cases(iter_coord, split_iter_coord, driver_iter,
                                              solver_iter, recurse, coord_lengths)

            # iterate over set of cases
            for iteration in iter_set:
                if iteration[1] is 'driver':
                    yield self.driver_cases.get_case(iteration[0])
                else:
                    yield self.solver_cases.get_case(iteration[0])

    def _find_child_cases(self, parent_iter_coord, split_parent_iter_coord, driver_iter,
                          solver_iter, recursive, coord_lengths):
        """
        Find all children of a given parent case.

        Parameters
        ----------
        parent_iter_coord : str
            Iteration coordinate of the parent case. If empty string, assumes root is parent.
        split_parent_iter_coord : [str]
            The split parent iteration coordinate.
        driver_iter : [(str)]
            The ordered list of driver iteration coordinates.
        solver_iter : [(str)]
            The ordered list of solver iteration coordinates.
        recursive : bool
            If True, will grab all successors recursively. Otherwise, will only return direct
            children.
        coord_lengths : [int]
            Sorted array of possible coordinate lengths. Used to determine if case is child
            of another case.

        Returns
        -------
        list of tuples
            List of tuples of the form ('iteration_coordinate', 'type of iteration')
        """
        ret = []
        par_len = len(split_parent_iter_coord)
        par_len_idx = coord_lengths.index(par_len if par_len is not 0 else 2)
        expected_child_length = coord_lengths[par_len_idx + 1] if par_len_idx <\
            len(coord_lengths) - 1 else -1
        if parent_iter_coord is '':  # CASE: grabbing children of 'root'
            if len(driver_iter) > 0:  # grabbing all driver cases
                for d in driver_iter:
                    ret.append((d[0], 'driver'))
                    if recursive:
                        ret += self._find_child_cases(d[0], _coord_split_re.split(d[0]),
                                                      driver_iter, solver_iter, recursive,
                                                      coord_lengths)
            elif len(solver_iter) > 0:  # grabbing first layer of solver iterations
                # find the iteration coordinate length of the first layer of solver iterations
                min_iter_len = -1
                if len(coord_lengths) > 1:
                    min_iter_len = coord_lengths[1]

                for s in solver_iter:
                    split_coord = _coord_split_re.split(s[0])
                    if len(split_coord) is min_iter_len:
                        ret.append((s[0], 'solver'))
                        if recursive:
                            ret += self._find_child_cases(s[0], split_coord, driver_iter,
                                                          solver_iter, recursive, coord_lengths)
        else:  # CASE: grabbing children of a case
            for s in solver_iter:
                if self._is_case_child(parent_iter_coord, s[0], expected_child_length):
                    ret.append((s[0], 'solver'))
                    if recursive:
                        ret += self._find_child_cases(s[0], _coord_split_re.split(s[0]),
                                                      driver_iter, solver_iter, recursive,
                                                      coord_lengths)

        return ret

    def _is_case_child(self, parent_coordinate, coordinate, expected_child_length):
        """
        Tell if the given case is a child case of the parent.

        Parameters
        ----------
        parent_coordinate : str
            The iteration coordinate of the potential parent.
        coordinate : str
            Iteration coordinate of the case we want to test.
        expected_child_length : int
            Expected length of the split child iteration coordinate

        Returns
        -------
        bool
            True if the given coordinate indicates that the case is a child of the
            given parent case. False otherwise.
        """
        split_coord = _coord_split_re.split(coordinate)
        if coordinate.startswith(parent_coordinate) and\
           len(split_coord) is expected_child_length:
            return True

        return False

    def list_inputs(self,
                    case=None,
                    values=True,
                    units=False,
                    hierarchical=True,
                    print_arrays=False,
                    out_stream=_DEFAULT_OUT_STREAM):
        """
        Return and optionally log a list of input names and other optional information.

        Also optionally logs the information to a user defined output stream.

        Parameters
        ----------
        case : Case, optional
            The case whose inputs will be listed. If None, gives all inputs. Defaults to None.
        values : bool, optional
            When True, display/return input values. Default is True.
        units : bool, optional
            When True, display/return units. Default is False.
        hierarchical : bool, optional
            When True, human readable output shows variables in hierarchical format.
        print_arrays : bool, optional
            When False, in the columnar display, just display norm of any ndarrays with size > 1.
            The norm is surrounded by vertical bars to indicate that it is a norm.
            When True, also display full values of the ndarray below the row. Format is affected
            by the values set with numpy.set_printoptions
            Default is False.
        out_stream : file-like object
            Where to send human readable output. Default is sys.stdout.
            Set to None to suppress.

        Returns
        -------
        list
            list of input names and other optional information about those inputs
        """
        meta = self._abs2meta
        if case is None:
            sys_vars = self._get_all_sysvars(False)
        else:
            sys_vars = self._get_case_sysvars(case, False)
        inputs = []

        if sys_vars is not None and len(sys_vars) > 0:
            for name in sys_vars:
                outs = {}
                if values:
                    outs['value'] = sys_vars[name]['value']
                if units:
                    outs['units'] = meta[name]['units']
                inputs.append((name, outs))

        if out_stream == _DEFAULT_OUT_STREAM:
            out_stream = sys.stdout

        if out_stream:
            if sys_vars is None:
                out_stream.write('WARNING: No system cases recorded. Make sure the recorder ' +
                                 'is attached to a system object\n')
            elif len(sys_vars) is 0:
                out_stream.write('WARNING: Inputs not recorded. Make sure your recording ' +
                                 'settings have record_inputs set to True\n')

            self._write_outputs('input', None, inputs, hierarchical, print_arrays, out_stream)

        return inputs

    def list_outputs(self,
                     case=None,
                     explicit=True, implicit=True,
                     values=True,
                     residuals=False,
                     residuals_tol=None,
                     units=False,
                     shape=False,
                     bounds=False,
                     scaling=False,
                     hierarchical=True,
                     print_arrays=False,
                     out_stream=_DEFAULT_OUT_STREAM):
        """
        Return and optionally log a list of output names and other optional information.

        Also optionally logs the information to a user defined output stream.

        Parameters
        ----------
        case : Case, optional
            The case whose outputs will be listed. If None, gives all outputs. Defaults to None.
        explicit : bool, optional
            include outputs from explicit components. Default is True.
        implicit : bool, optional
            include outputs from implicit components. Default is True.
        values : bool, optional
            When True, display/return output values. Default is True.
        residuals : bool, optional
            When True, display/return residual values. Default is False.
        residuals_tol : float, optional
            If set, limits the output of list_outputs to only variables where
            the norm of the resids array is greater than the given 'residuals_tol'.
            Default is None.
        units : bool, optional
            When True, display/return units. Default is False.
        shape : bool, optional
            When True, display/return the shape of the value. Default is False.
        bounds : bool, optional
            When True, display/return bounds (lower and upper). Default is False.
        scaling : bool, optional
            When True, display/return scaling (ref, ref0, and res_ref). Default is False.
        hierarchical : bool, optional
            When True, human readable output shows variables in hierarchical format.
        print_arrays : bool, optional
            When False, in the columnar display, just display norm of any ndarrays with size > 1.
            The norm is surrounded by vertical bars to indicate that it is a norm.
            When True, also display full values of the ndarray below the row. Format  is affected
            by the values set with numpy.set_printoptions
            Default is False.
        out_stream : file-like
            Where to send human readable output. Default is sys.stdout.
            Set to None to suppress.

        Returns
        -------
        list
            list of output names and other optional information about those outputs
        """
        meta = self._abs2meta
        expl_outputs = []
        impl_outputs = []
        sys_vars = self._get_all_sysvars()

        if case is None:
            sys_vars = self._get_all_sysvars()
        else:
            sys_vars = self._get_case_sysvars(case)

        if sys_vars is not None and len(sys_vars) > 0:
            for name in sys_vars:
                if residuals_tol and \
                   sys_vars[name]['residuals'] is not 'Not Recorded' and \
                   np.linalg.norm(sys_vars[name]['residuals']) < residuals_tol:
                    continue
                outs = {}
                if values:
                    outs['value'] = sys_vars[name]['value']
                if residuals:
                    outs['resids'] = sys_vars[name]['residuals']
                if units:
                    outs['units'] = meta[name]['units']
                if shape:
                    outs['shape'] = sys_vars[name]['value'].shape
                if bounds:
                    outs['lower'] = meta[name]['lower']
                    outs['upper'] = meta[name]['upper']
                if scaling:
                    outs['ref'] = meta[name]['ref']
                    outs['ref0'] = meta[name]['ref0']
                    outs['res_ref'] = meta[name]['res_ref']
                if meta[name]['explicit']:
                    expl_outputs.append((name, outs))
                else:
                    impl_outputs.append((name, outs))

        if out_stream == _DEFAULT_OUT_STREAM:
            out_stream = sys.stdout

        if out_stream:
            if sys_vars is None:
                out_stream.write('WARNING: No system cases recorded. Make sure the recorder ' +
                                 'is attached to a system object\n')
            elif len(sys_vars) is 0:
                out_stream.write('WARNING: Outputs not recorded. Make sure your recording ' +
                                 'settings have record_outputs set to True\n')

            if explicit:
                self._write_outputs('output', 'Explicit', expl_outputs, hierarchical, print_arrays,
                                    out_stream)

            if implicit:
                self._write_outputs('output', 'Implicit', impl_outputs, hierarchical, print_arrays,
                                    out_stream)

        if explicit and implicit:
            return expl_outputs + impl_outputs
        elif explicit:
            return expl_outputs
        elif implicit:
            return impl_outputs
        else:
            raise RuntimeError('You have excluded both Explicit and Implicit components.')

    def _get_case_sysvars(self, case, get_outputs=True):
        """
        Get the set of output or input variables and their values for a given case.

        Parameters
        ----------
        case : Case
            The case whose variables will be returned.
        get_outputs : bool, optional
            indicates if the returned set should contain outputs. If false, returns inputs.

        Returns
        -------
        dictionary
            dictionary of global variable names to their values. None if no system iterations
            were recorded.
        """
        variables = {}
        if get_outputs and case.outputs is None:
            return variables

        if get_outputs:
            for abs_name in case.outputs.absolute_names():
                variables[abs_name] = {'value': case.outputs[abs_name]}
                if case.residuals and abs_name in case.residuals.absolute_names():
                    variables[abs_name]['residuals'] = case.residuals[abs_name]
                else:
                    variables[abs_name]['residuals'] = 'Not Recorded'
        elif case.inputs is not None:
            for abs_name in case.inputs.absolute_names():
                if abs_name not in variables:
                    variables[abs_name] = {'value': case.inputs[abs_name]}

        return variables

    def _get_all_sysvars(self, get_outputs=True):
        """
        Get the set of output or input variables and their values.

        Parameters
        ----------
        get_outputs : bool, optional
            indicates if the returned set should contain outputs. If false, returns inputs.

        Returns
        -------
        dictionary
            dictionary of global variable names to their values. None if no system iterations
            were recorded.
        """
        coords = self.system_cases._case_keys

        # store the iteration coordinates without iteration numbers.
        # coord_map intializes each iter_key to False, indicating we haven't
        # grabbed values from this system
        coord_map = {}
        for c in coords:
            split_iter = _coord_split_re.split(c)
            iter_key = ':'.join(split_iter)
            coord_map[iter_key] = False

        # didn't record any system iterations, return None
        if len(coord_map) is 0:
            return None

        variables = {}
        iteration_num = -1
        # iterate over cases from end to start, unless we've grabbed values from
        # every system
        while not self._has_all_values(coord_map):
            iteration = self.system_cases._case_keys[iteration_num]
            iteration_num -= 1
            split_iter = _coord_split_re.split(iteration)
            iter_key = ':'.join(split_iter)

            # if coord_map[iter_key] is False, we haven't grabbed variable values
            # from this system
            if not coord_map[iter_key]:
                coord_map[iter_key] = True
                case = self.system_cases.get_case(iteration)
                if get_outputs and case.outputs is None:
                    continue
                if not get_outputs and case.inputs is None:
                    continue

                if get_outputs:
                    for abs_name in case.outputs.absolute_names():
                        if abs_name not in variables:
                            variables[abs_name] = {'value': case.outputs[abs_name]}
                            if case.residuals and abs_name in case.residuals.absolute_names():
                                variables[abs_name]['residuals'] = case.residuals[abs_name]
                            else:
                                variables[abs_name]['residuals'] = 'Not Recorded'
                elif case.inputs is not None:
                    for abs_name in case.inputs.absolute_names():
                        if abs_name not in variables:
                            variables[abs_name] = {'value': case.inputs[abs_name]}

        return variables

    def _has_all_values(self, coord_map):
        """
        Tell if all variables from every recorded system have been iterated over.

        Parameters
        ----------
        coord_map : dict
            maps stripped iteration coordinates to a bool indicating whether or not the system(s)
            associated with that iteration coordinate have been iterated over.

        Returns
        -------
        bool
            True if coord_map is True for each key, False otherwise.
        """
        for coord in coord_map:
            if not coord_map[coord]:
                return False
        return True

    def _write_outputs(self, in_or_out, comp_type, outputs, hierarchical, print_arrays,
                       out_stream):
        """
        Write table of variable names, values, residuals, and metadata to out_stream.

        The output values could actually represent input variables.
        In this context, outputs refers to the data that is being logged to an output stream.

        Parameters
        ----------
        in_or_out : str, 'input' or 'output'
            indicates whether the values passed in are from inputs or output variables.
        comp_type : str, 'Explicit' or 'Implicit'
            the type of component with the output values.
        outputs : list
            list of (name, dict of vals and metadata) tuples.
        hierarchical : bool
            When True, human readable output shows variables in hierarchical format.
        print_arrays : bool
            When False, in the columnar display, just display norm of any ndarrays with size > 1.
            The norm is surrounded by vertical bars to indicate that it is a norm.
            When True, also display full values of the ndarray below the row. Format  is affected
            by the values set with numpy.set_printoptions
            Default is False.
        out_stream : file-like object
            Where to send human readable output.
            Set to None to suppress.
        """
        if out_stream is None:
            return

        # Make a dict of outputs. Makes it easier to work with in this method
        dict_of_outputs = OrderedDict()
        for name, vals in outputs:
            dict_of_outputs[name] = vals

        allprocs_abs_names = {
            'input': dict_of_outputs.keys(),
            'output': dict_of_outputs.keys()
        }

        write_outputs(in_or_out, comp_type, dict_of_outputs, hierarchical, print_arrays, out_stream,
                      'model', allprocs_abs_names)


class DriverCases(BaseCases):
    """
    Case specific to the entries that might be recorded in a Driver iteration.

    Attributes
    ----------
    _var_settings : dict
        Dictionary mapping absolute variable names to variable settings.
    """

    def __init__(self, filename, format_version, abs2prom, abs2meta, prom2abs, var_settings):
        """
        Initialize.

        Parameters
        ----------
        filename : str
            The name of the recording file from which to instantiate the case reader.
        format_version : int
            The version of the format assumed when loading the file.
        abs2prom : {'input': dict, 'output': dict}
            Dictionary mapping absolute names to promoted names.
        abs2meta : dict
            Dictionary mapping absolute variable names to variable metadata.
        prom2abs : {'input': dict, 'output': dict}
            Dictionary mapping promoted names to absolute names.
        var_settings : dict
            Dictionary mapping absolute variable names to variable settings.
        """
        super(DriverCases, self).__init__(filename, format_version, abs2prom, abs2meta, prom2abs)
        self._var_settings = var_settings

    def _extract_case_from_row(self, row):
        """
        Pull data out of a queried SQLite row.

        Parameters
        ----------
        row : (id, counter, iter_coordinate, timestamp, success, msg, inputs, outputs)
            Queried SQLite driver table row.

        Returns
        -------
        DriverCase
            Case for associated row.
        """
        idx, counter, iteration_coordinate, timestamp, success, msg, inputs_text, \
            outputs_text, = row

        if self.format_version >= 3:
            inputs_array = json_to_np_array(inputs_text, self._abs2meta)
            outputs_array = json_to_np_array(outputs_text, self._abs2meta)
        elif self.format_version in (1, 2):
            inputs_array = blob_to_array(inputs_text)
            outputs_array = blob_to_array(outputs_text)

        case = DriverCase(self.filename, counter, iteration_coordinate, timestamp,
                          success, msg, inputs_array, outputs_array,
                          self._prom2abs, self._abs2prom, self._abs2meta, self._var_settings)
        return case

    def load_cases(self):
        """
        Load all driver cases into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM driver_iterations")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case

    def cases(self):
        """
        Iterate over all driver cases, while storing them into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM driver_iterations")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case
                yield case

    def get_case(self, case_id, scaled=False):
        """
        Get a case from the database.

        Parameters
        ----------
        case_id : int or str
            The integer index or string-identifier of the case to be retrieved.
        scaled : bool
            If True, return variables scaled. Otherwise, return physical values.

        Returns
        -------
            An instance of a Driver Case populated with data from the
            specified case/iteration.
        """
        # check to see if we've already cached this case
        iteration_coordinate = self.get_iteration_coordinate(case_id)
        if iteration_coordinate in self._cases:
            case = self._cases[iteration_coordinate]
        else:
            # Get an unscaled case if does not already exist in _cases
            with sqlite3.connect(self.filename) as con:
                cur = con.cursor()
                cur.execute("SELECT * FROM driver_iterations WHERE "
                            "iteration_coordinate=:iteration_coordinate",
                            {"iteration_coordinate": iteration_coordinate})
                # Initialize the Case object from the iterations data
                row = cur.fetchone()
            con.close()

            case = self._extract_case_from_row(row)

            # save so we don't query again
            self._cases[case.iteration_coordinate] = case

        if scaled:
            # We have to do some scaling first before we return it
            # Need to make a copy, otherwise we modify the object in the cache
            case = deepcopy(case)
            case.scale()

        return case


class DriverDerivativeCases(BaseCases):
    """
    Case specific to the entries that might be recorded in a Driver derivatives computation.
    """

    def _extract_case_from_row(self, row):
        """
        Pull data out of a queried SQLite row.

        Parameters
        ----------
        row : (id, counter, iter_coordinate, timestamp, success, msg, totals)
            Queried SQLite driver derivatives table row.

        Returns
        -------
        DriverDerivativesCase
            Case for associated row.
        """
        idx, counter, iteration_coordinate, timestamp, success, msg, totals_blob = row

        totals_array = blob_to_array(totals_blob)

        case = DriverDerivativesCase(self.filename, counter, iteration_coordinate,
                                     timestamp, success, msg, totals_array,
                                     self._prom2abs, self._abs2prom, self._abs2meta)
        return case

    def load_cases(self):
        """
        Load all driver cases into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM driver_derivatives")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case

    def get_case(self, case_id):
        """
        Get a case from the database.

        Parameters
        ----------
        case_id : int or str
            The integer index or string-identifier of the case to be retrieved.

        Returns
        -------
            An instance of a Driver Case populated with data from the
            specified case/iteration.
        """
        # check to see if we've already cached this case
        iteration_coordinate = self.get_iteration_coordinate(case_id)
        if iteration_coordinate in self._cases:
            return self._cases[iteration_coordinate]

        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM driver_derivatives WHERE "
                        "iteration_coordinate=:iteration_coordinate",
                        {"iteration_coordinate": iteration_coordinate})
            # Initialize the Case object from the iterations data
            row = cur.fetchone()
        con.close()

        case = self._extract_case_from_row(row)

        # save so we don't query again
        self._cases[case.iteration_coordinate] = case
        return case


class ProblemCases(BaseCases):
    """
    Case specific to the entries that might be recorded in a Driver iteration.
    """

    def _extract_case_from_row(self, row):
        """
        Pull data out of a queried SQLite row.

        Parameters
        ----------
        row : (id, counter, iter_coordinate, timestamp, success, msg, outputs)
            Queried SQLite problems table row.

        Returns
        -------
        ProblemCase
            Case for associated row.
        """
        idx, counter, case_name, timestamp, success, msg, \
            outputs_text, = row

        if self.format_version >= 3:
            outputs_array = json_to_np_array(outputs_text, self._abs2meta)
        elif self.format_version in (1, 2):
            outputs_array = blob_to_array(outputs_text)

        case = ProblemCase(self.filename, counter, case_name, timestamp,
                           success, msg, outputs_array, self._prom2abs,
                           self._abs2prom, self._abs2meta)
        return case

    def load_cases(self):
        """
        Load all problem cases into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM problem_cases")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case

    def cases(self):
        """
        Iterate over all problem cases, while storing them into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM problem_cases")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case
                yield case

    def get_case(self, case_name):
        """
        Get a case from the database.

        Parameters
        ----------
        case_name : str
            The string-identifier of the case to be retrieved.

        Returns
        -------
            An instance of a Driver Case populated with data from the
            specified case/iteration.
        """
        # check to see if we've already cached this case
        if case_name in self._cases:
            return self._cases[case_name]

        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM problem_cases WHERE "
                        "case_name=:case_name",
                        {"case_name": case_name})
            # Initialize the Case object from the iterations data
            row = cur.fetchone()
        con.close()

        case = self._extract_case_from_row(row)

        # save so we don't query again
        self._cases[case_name] = case
        return case


class SystemCases(BaseCases):
    """
    Case specific to the entries that might be recorded in a System iteration.
    """

    def _extract_case_from_row(self, row):
        """
        Pull data out of a queried SQLite row.

        Parameters
        ----------
        row : (id, counter, iter_coordinate, timestamp, success, msg, inputs, outputs, residuals)
            Queried SQLite systems table row.

        Returns
        -------
        SystemCase
            Case for associated row.
        """
        idx, counter, iteration_coordinate, timestamp, success, msg, inputs_text,\
            outputs_text, residuals_text = row

        if self.format_version >= 3:
            inputs_array = json_to_np_array(inputs_text, self._abs2meta)
            outputs_array = json_to_np_array(outputs_text, self._abs2meta)
            residuals_array = json_to_np_array(residuals_text, self._abs2meta)
        elif self.format_version in (1, 2):
            inputs_array = blob_to_array(inputs_text)
            outputs_array = blob_to_array(outputs_text)
            residuals_array = blob_to_array(residuals_text)

        case = SystemCase(self.filename, counter, iteration_coordinate, timestamp,
                          success, msg, inputs_array, outputs_array, residuals_array,
                          self._prom2abs, self._abs2prom, self._abs2meta)
        return case

    def load_cases(self):
        """
        Load all system cases into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM system_iterations")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case

    def get_case(self, case_id):
        """
        Get a case from the database.

        Parameters
        ----------
        case_id : int or str
            The integer index or string-identifier of the case to be retrieved.

        Returns
        -------
            An instance of a System Case populated with data from the
            specified case/iteration.
        """
        # check to see if we've already cached this case
        iteration_coordinate = self.get_iteration_coordinate(case_id)
        if iteration_coordinate in self._cases:
            return self._cases[iteration_coordinate]

        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM system_iterations WHERE "
                        "iteration_coordinate=:iteration_coordinate",
                        {"iteration_coordinate": iteration_coordinate})
            # Initialize the Case object from the iterations data
            row = cur.fetchone()
        con.close()

        case = self._extract_case_from_row(row)

        # save so we don't query again
        self._cases[case.iteration_coordinate] = case
        return case


class SolverCases(BaseCases):
    """
    Case specific to the entries that might be recorded in a Solver iteration.
    """

    def _extract_case_from_row(self, row):
        """
        Pull data out of a queried SQLite row.

        Parameters
        ----------
        row : (id, counter, iter_coordinate, timestamp, success, msg, abs_err, rel_err,
               inputs, outputs, residuals)
            Queried SQLite solvers table row.

        Returns
        -------
        SolverCase
            Case for associated row.
        """
        idx, counter, iteration_coordinate, timestamp, success, msg, abs_err, rel_err, \
            input_text, output_text, residuals_text = row

        if self.format_version >= 3:
            input_array = json_to_np_array(input_text, self._abs2meta)
            output_array = json_to_np_array(output_text, self._abs2meta)
            residuals_array = json_to_np_array(residuals_text, self._abs2meta)
        elif self.format_version in (1, 2):
            input_array = blob_to_array(input_text)
            output_array = blob_to_array(output_text)
            residuals_array = blob_to_array(residuals_text)

        case = SolverCase(self.filename, counter, iteration_coordinate, timestamp,
                          success, msg, abs_err, rel_err, input_array, output_array,
                          residuals_array, self._prom2abs, self._abs2prom, self._abs2meta)
        return case

    def load_cases(self):
        """
        Load all solver cases into memory.
        """
        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM solver_iterations")
            rows = cur.fetchall()
            for row in rows:
                case = self._extract_case_from_row(row)
                self._cases[case.iteration_coordinate] = case

    def get_case(self, case_id):
        """
        Get a case from the database.

        Parameters
        ----------
        case_id : int or str
            The integer index or string-identifier of the case to be retrieved.

        Returns
        -------
            An instance of a solver Case populated with data from the
            specified case/iteration.
        """
        # check to see if we've already cached this case
        iteration_coordinate = self.get_iteration_coordinate(case_id)
        if iteration_coordinate in self._cases:
            return self._cases[iteration_coordinate]

        with sqlite3.connect(self.filename) as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM solver_iterations WHERE "
                        "iteration_coordinate=:iteration_coordinate",
                        {"iteration_coordinate": iteration_coordinate})
            # Initialize the Case object from the iterations data
            row = cur.fetchone()
        con.close()

        case = self._extract_case_from_row(row)

        # save so we don't query again
        self._cases[iteration_coordinate] = case
        return case